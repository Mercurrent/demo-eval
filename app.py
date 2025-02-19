from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pymongo import MongoClient
import os
from datetime import datetime, timezone
import csv
import random
import json
from bson import ObjectId
from metrics import calculate_metrics, detect_column_type
from dotenv import load_dotenv
from pydantic import BaseModel
from bson.errors import InvalidId

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Load environment variables and setup
load_dotenv()

# Ensure the uploads directory exists
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Update database connection
def get_db_connection():
    """Connect to Cosmos DB emulator using MongoDB API"""
    connection_string = os.getenv('DB_CONNECTION_STRING', 'mongodb://localhost:27017/')
    client = MongoClient(connection_string)
    
    # Create database if it doesn't exist
    db = client['evaluation_db']
    
    # Create collections if they don't exist
    collections = ['use_cases', 'label_files', 'evaluation_sets', 'extraction_results', 'evaluation_iterations']
    for collection in collections:
        if collection not in db.list_collection_names():
            db.create_collection(collection)
    
    return db

def split_csv_rows(file_path):
    """Split the rows of a CSV file into golden and test sets.
    Validates document_ids and ensures they are unique."""
    try:
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Validate CSV has required column
            if 'document_id' not in reader.fieldnames:
                raise ValueError("CSV file must contain 'document_id' column")
            
            rows = list(reader)
            
            # Validate document_ids
            document_ids = [row['document_id'] for row in rows]
            if len(document_ids) != len(set(document_ids)):
                raise ValueError("Duplicate document_ids found in CSV")
            
            if not all(document_ids):  # Check for empty document_ids
                raise ValueError("Empty document_ids found in CSV")
            
            # Shuffle and split the data
            random.shuffle(rows)
            split_index = len(rows) // 2
            
            golden_set = [row['document_id'] for row in rows[:split_index]]
            test_set = [row['document_id'] for row in rows[split_index:]]
            
            return golden_set, test_set
            
    except csv.Error:
        raise ValueError("Invalid CSV file format")

def get_csv_content(file_path, document_ids, column_types=None):
    """Read CSV file and return rows for specified document IDs with proper type conversion"""
    try:
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = []
            for row in reader:
                if document_ids is None or row['document_id'] in document_ids:
                    # Convert values according to detected types
                    if column_types:
                        for field, value in row.items():
                            if field != 'document_id':
                                try:
                                    if column_types.get(field) == 'integer':
                                        row[field] = int(value) if value.strip() else 0
                                    elif column_types.get(field) == 'float':
                                        row[field] = float(value) if value.strip() else 0.0
                                    elif column_types.get(field) == 'boolean':
                                        row[field] = value.lower() in ('true', '1', 'yes', 'y')
                                    # Keep as string if type is string or unknown
                                except (ValueError, TypeError):
                                    print(f"Warning: Could not convert {field} value '{value}' to {column_types.get(field)}")
                    rows.append(row)
            return rows
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}, {file_path}")
        return []

@app.get("/")
async def index():
    return "Welcome to the Evaluation Web-Service!"

@app.get("/create_use_case.html")
async def create_use_case_page(request: Request):
    return templates.TemplateResponse('create_use_case.html', {"request": request})

# Add Pydantic model for use case creation
class UseCase(BaseModel):
    name: str
    success_criteria: str = ""

@app.post("/create_use_case")
async def create_use_case(use_case: UseCase):
    try:
        db = get_db_connection()
        
        # Check if use case with this name already exists
        existing = db.use_cases.find_one({'name': use_case.name})
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Use case with name '{use_case.name}' already exists"
            )
        
        # Insert new use case
        result = db.use_cases.insert_one({
            'name': use_case.name,
            'success_criteria': use_case.success_criteria,
            'created_at': datetime.now(timezone.utc)
        })
        
        if not result.inserted_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create use case"
            )

        return JSONResponse(
            content={'message': 'Use case created successfully'},
            status_code=201
        )
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"Error creating use case: {str(e)}"
        )

@app.get("/upload_label_file.html")
async def upload_label_file_page(request: Request):
    return templates.TemplateResponse('upload_label_file.html', {"request": request})

@app.post("/upload_label_file")
async def upload_label_file(
    use_case_name: str = Form(...),
    file: UploadFile = File(...)
):
    file_path = None
    try:
        # File validation and saving
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail='Only CSV files are allowed')

        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        with open(file_path, 'wb') as f:
            f.write(file.file.read())

        db = get_db_connection()
        use_cases = db.use_cases
        use_case = use_cases.find_one({'name': use_case_name})

        if not use_case:
            os.remove(file_path)
            raise HTTPException(status_code=404, detail='Use case not found')

        use_case_id = use_case['_id']
        
        # Delete old label files and their data
        old_label_files = db.label_files.find({'use_case_id': use_case_id})
        for old_file in old_label_files:
            if os.path.exists(old_file['file_path']):
                os.remove(old_file['file_path'])
        db.label_files.delete_many({'use_case_id': use_case_id})
        db.evaluation_sets.delete_many({'use_case_id': use_case_id})

        # Validate CSV structure
        try:
            golden_set, test_set = split_csv_rows(file_path)
        except ValueError as ve:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=str(ve))

        # Detect column types
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            
            # Detect column types
            column_types = {}
            for field in reader.fieldnames:
                if field not in ['document_id', 'row_id']:  # Explicitly exclude row_id
                    values = [row[field] for row in rows]
                    column_types[field] = detect_column_type(values)

        # Store file metadata with validation status
        label_files = db.label_files
        label_file = {
            'use_case_id': use_case_id,
            'file_path': file_path,
            'original_filename': file.filename,
            'uploaded_at': datetime.now(timezone.utc),
            'file_size': os.path.getsize(file_path),
            'status': 'processed',
            'document_count': len(golden_set) + len(test_set),
            'validation_status': 'valid',
            'column_types': column_types
        }
        label_file_id = label_files.insert_one(label_file).inserted_id

        # Store the evaluation sets
        evaluation_sets = db.evaluation_sets
        evaluation_set = {
            'use_case_id': use_case_id,
            'label_file_id': label_file_id,
            'gold_set': golden_set,
            'test_set': test_set,
            'created_at': datetime.now(timezone.utc),
            'total_documents': len(golden_set) + len(test_set)
        }
        evaluation_sets.insert_one(evaluation_set)

        return JSONResponse({
            'message': 'Label file uploaded and processed successfully',
            'file_id': str(label_file_id),
            'golden_set_size': len(golden_set),
            'test_set_size': len(test_set)
        }, status_code=201)

    except Exception as e:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/generate_report/{evaluation_iteration_id}")
async def generate_report(evaluation_iteration_id: int):
    db = get_db_connection()
    evaluation_iterations = db.evaluation_iterations

    evaluation_iteration = evaluation_iterations.find_one({'_id': evaluation_iteration_id})
    if not evaluation_iteration:
        raise HTTPException(status_code=404, detail='Evaluation iteration not found')

    use_cases = db.use_cases
    use_case = use_cases.find_one({'_id': evaluation_iteration['use_case_id']})

    extraction_results = db.extraction_results
    extraction_result = extraction_results.find_one({'_id': evaluation_iteration['extraction_result_id']})

    # Generate evaluation metrics (dummy data for now)
    report = {
        'use_case': use_case,
        'evaluation_iteration': evaluation_iteration,
        'extraction_result': extraction_result,
        'gold_set_report': {
            'overall_quality_metrics': {'precision': 0.9, 'recall': 0.85},
            'quality_metrics_per_field': {'field1': {'precision': 0.92, 'recall': 0.88}},
            'average_latency': 0.5,
            'cost_metrics': {'average_cost': 0.1, 'cost_percentiles': [0.05, 0.1, 0.15]}
        },
        'test_set_report': {
            'overall_quality_metrics': {'precision': 0.85, 'recall': 0.8},
            'quality_metrics_per_field': {'field1': {'precision': 0.87, 'recall': 0.82}},
            'average_latency': 0.6,
            'cost_metrics': {'average_cost': 0.12, 'cost_percentiles': [0.06, 0.12, 0.18]}
        },
        'detailed_report': 'Detailed report data here',
        'error_report': 'Error report data here'
    }

    return JSONResponse(report)

@app.get("/view_report/{evaluation_iteration_id}")
async def view_report(request: Request, evaluation_iteration_id: int):
    return templates.TemplateResponse('view_report.html', {
        "request": request,
        "evaluation_iteration_id": evaluation_iteration_id
    })

@app.get("/use_case/{use_case_name}")
async def view_use_case(request: Request, use_case_name: str):
    """Display use case details and associated label files"""
    try:
        db = get_db_connection()
        
        # Find the use case - use _id for partitioning
        use_case = db.use_cases.find_one({
            'name': use_case_name
        })
        if not use_case:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "message": "Use case not found"},
                status_code=404
            )

        # Get only the latest label file - use composite index
        latest_file = db.label_files.find_one(
            {'use_case_id': use_case['_id']},
            sort=[('_ts', -1)]  # Use _ts instead of uploaded_at for Cosmos DB
        )
        
        associated_files = [latest_file] if latest_file else []

        # Get evaluation sets and test set content for each label file
        evaluation_sets = db.evaluation_sets
        for file in associated_files:
            eval_set = evaluation_sets.find_one({'label_file_id': file['_id']})
            if eval_set:
                file['golden_set_size'] = len(eval_set['gold_set'])
                file['test_set_size'] = len(eval_set['test_set'])
                file['total_documents'] = eval_set['total_documents']
                
                # Get test set content from CSV file
                test_set_content = get_csv_content(
                    file['file_path'], 
                    eval_set['test_set'],
                    column_types=file.get('column_types', {})
                )
                file['test_set_content'] = test_set_content
                
                # Get CSV headers for display
                if test_set_content:
                    file['csv_headers'] = list(test_set_content[0].keys())

        # Get previous evaluations
        evaluations = list(db.evaluation_iterations.find(
            {'use_case_id': use_case['_id']}
        ).sort('created_at', -1))

        # Add label file names to evaluations
        for eval in evaluations:
            label_file = db.label_files.find_one({'_id': eval['label_file_id']})
            if label_file:
                eval['label_file_name'] = label_file['original_filename']

        return templates.TemplateResponse(
            "view_use_case.html",
            {
                "request": request,
                "use_case": use_case,
                "label_files": associated_files,
                "evaluations": evaluations
            }
        )

    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": str(e)},
            status_code=500
        )

@app.get("/use_cases")
async def list_use_cases(request: Request):
    """Display list of all use cases"""
    try:
        db = get_db_connection()
        all_use_cases = list(db.use_cases.find().sort('created_at', -1))
        return templates.TemplateResponse(
            "use_cases.html",
            {"request": request, "use_cases": all_use_cases}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": str(e)},
            status_code=500
        )

@app.post("/upload_extraction_result/{use_case_name}")
async def upload_extraction_result(
    use_case_name: str,
    file: UploadFile = File(...)
):
    try:
        if not file:
            raise HTTPException(status_code=400, detail='No file provided')
            
        if not file.filename.endswith('.json'):
            raise HTTPException(status_code=400, detail='Only JSON files are allowed')
            
        db = get_db_connection()
        
        # Find use case
        use_case = db.use_cases.find_one({'name': use_case_name})
        if not use_case:
            raise HTTPException(status_code=404, detail=f'Use case "{use_case_name}" not found')
            
        # Check if label file exists first
        label_file = db.label_files.find_one(
            {'use_case_id': use_case['_id']},
            sort=[('uploaded_at', -1)]
        )
        if not label_file:
            raise HTTPException(
                status_code=400, 
                detail='Please upload a label file before uploading extraction results'
            )
            
        # Find latest evaluation set for the use case
        latest_eval_set = db.evaluation_sets.find_one(
            {'use_case_id': use_case['_id']},
            sort=[('created_at', -1)]
        )
        
        if not latest_eval_set:
            raise HTTPException(
                status_code=400, 
                detail='No evaluation set found. Please ensure label file was processed correctly'
            )

        # Load and validate JSON content
        try:
            file_content = await file.read()
            await file.seek(0)
            extraction_results = json.loads(file_content.decode('utf-8'))
            
            # Get column types from label file
            column_types = label_file.get('column_types', {})
            
            # Convert extraction results to match CSV types
            for result in extraction_results:
                if not isinstance(result, dict):
                    raise HTTPException(status_code=400, detail='Each result must be an object')
                    
                for field, value in result.items():
                    if field == 'document_id':
                        continue
                        
                    target_type = column_types.get(field)
                    if target_type:
                        try:
                            if target_type == 'integer':
                                result[field] = int(value) if value else 0
                            elif target_type == 'float':
                                result[field] = float(value) if value else 0.0
                            elif target_type == 'boolean':
                                if isinstance(value, str):
                                    result[field] = value.lower() in ('true', '1', 'yes', 'y')
                                else:
                                    result[field] = bool(value)
                            elif target_type == 'string':
                                result[field] = str(value) if value is not None else ''
                            else:
                                # Keep original type if unknown
                                continue
                        except (ValueError, TypeError):
                            raise HTTPException(
                                status_code=400,
                                detail=f'Invalid value for field {field}: {value}. Expected type: {target_type}'
                            )

            # Validate document IDs match
            label_doc_ids = set(row['document_id'] for row in get_csv_content(label_file['file_path'], None, column_types))
            result_doc_ids = set(row['document_id'] for row in extraction_results)
            print(extraction_results)

            if not result_doc_ids.issubset(label_doc_ids):
                raise HTTPException(
                    status_code=400,
                    detail=f'Document IDs in extraction results do not match label file, {result_doc_ids.difference(label_doc_ids)} are missing in label set'
                )
            
            # Store extraction results
            extraction_result = {
                'use_case_id': use_case['_id'],
                'label_file_id': label_file['_id'],
                'results': extraction_results,
                'created_at': datetime.now(timezone.utc)
            }
            
            result_id = db.extraction_results.insert_one(extraction_result).inserted_id
            
            # Calculate metrics for different sets
            test_set_metrics = calculate_metrics(
                get_csv_content(label_file['file_path'], None, column_types=label_file.get('column_types', {})),
                extraction_results,
                latest_eval_set['test_set']
            )
            
            golden_set_metrics = calculate_metrics(
                get_csv_content(label_file['file_path'], None, column_types=label_file.get('column_types', {})),
                extraction_results,
                latest_eval_set['gold_set']
            )
            
            total_metrics = calculate_metrics(
                get_csv_content(label_file['file_path'], None, column_types=label_file.get('column_types', {})),
                extraction_results,
                list(label_doc_ids)
            )
            
            # Create evaluation iteration
            evaluation_iteration = {
                'use_case_id': use_case['_id'],
                'extraction_result_id': result_id,
                'label_file_id': label_file['_id'],
                'created_at': datetime.now(timezone.utc),
                'metrics': {
                    'test_set': test_set_metrics,
                    'golden_set': golden_set_metrics,
                    'total': total_metrics
                }
            }
            
            iteration_id = db.evaluation_iterations.insert_one(evaluation_iteration).inserted_id
            
            return JSONResponse({
                'message': 'Extraction results uploaded and evaluated successfully',
                'evaluation_iteration_id': str(iteration_id),
                'metrics_summary': {
                    'test_set': test_set_metrics,
                    'golden_set': golden_set_metrics,
                    'total': total_metrics
                }
            }, status_code=201)
            
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f'Invalid JSON format: {str(e)}')
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/evaluation/{evaluation_iteration_id}")
async def view_evaluation(request: Request, evaluation_iteration_id: str):
    try:
        db = get_db_connection()
        
        # Safely convert string ID to ObjectId
        try:
            eval_id = ObjectId(evaluation_iteration_id)
        except InvalidId:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "message": "Invalid evaluation ID format"},
                status_code=400
            )
        
        # Find evaluation iteration
        evaluation = db.evaluation_iterations.find_one({'_id': eval_id})
        if not evaluation:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "message": "Evaluation not found"},
                status_code=404
            )
            
        # Get related data
        try:
            use_case = db.use_cases.find_one({'_id': evaluation['use_case_id']})
            label_file = db.label_files.find_one({'_id': evaluation['label_file_id']})
            extraction_result = db.extraction_results.find_one({'_id': evaluation['extraction_result_id']})
            
            if not all([use_case, label_file, extraction_result]):
                raise ValueError("Missing related data")
            
            # Get test set content for comparison
            eval_set = db.evaluation_sets.find_one({'label_file_id': label_file['_id']})
            if not eval_set:
                raise ValueError("Evaluation set not found")
                
            test_set_labels = get_csv_content(
                label_file['file_path'], 
                eval_set['test_set'],
                column_types=label_file.get('column_types', {})
            )
            test_set_results = [r for r in extraction_result['results'] 
                               if r['document_id'] in eval_set['test_set']]
            
            return templates.TemplateResponse(
                'view_evaluation.html',
                {
                    "request": request,
                    "evaluation": evaluation,
                    "use_case": use_case,
                    "label_file": label_file,
                    "test_set_labels": test_set_labels,
                    "test_set_results": test_set_results
                }
            )
            
        except Exception as e:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "message": f"Error loading evaluation data: {str(e)}"},
                status_code=500
            )
        
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": f"Server error: {str(e)}"},
            status_code=500
        )

@app.delete("/use_case/{use_case_name}")
async def delete_use_case(use_case_name: str):
    try:
        db = get_db_connection()
        
        # Find use case
        use_case = db.use_cases.find_one({'name': use_case_name})
        if not use_case:
            raise HTTPException(status_code=404, detail='Use case not found')
            
        # Delete associated label files
        label_files = db.label_files.find({'use_case_id': use_case['_id']})
        for label_file in label_files:
            if os.path.exists(label_file['file_path']):
                os.remove(label_file['file_path'])
                
        # Delete all related data
        db.label_files.delete_many({'use_case_id': use_case['_id']})
        db.evaluation_sets.delete_many({'use_case_id': use_case['_id']})
        db.extraction_results.delete_many({'use_case_id': use_case['_id']})
        db.evaluation_iterations.delete_many({'use_case_id': use_case['_id']})
        
        # Delete use case
        db.use_cases.delete_one({'_id': use_case['_id']})
        
        return JSONResponse({'message': 'Use case and all related data deleted successfully'})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/evaluation/{evaluation_iteration_id}")
async def delete_evaluation(evaluation_iteration_id: str):
    try:
        db = get_db_connection()
        
        # Convert string ID to ObjectId
        try:
            eval_id = ObjectId(evaluation_iteration_id)
        except InvalidId:
            raise HTTPException(status_code=400, detail='Invalid evaluation ID format')
            
        # Find evaluation
        evaluation = db.evaluation_iterations.find_one({'_id': eval_id})
        if not evaluation:
            raise HTTPException(status_code=404, detail='Evaluation not found')
            
        # Delete extraction results
        db.extraction_results.delete_one({'_id': evaluation['extraction_result_id']})
        
        # Delete evaluation
        db.evaluation_iterations.delete_one({'_id': eval_id})
        
        return JSONResponse({'message': 'Evaluation and results deleted successfully'})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
