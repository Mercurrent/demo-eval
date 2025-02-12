from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
import os
from datetime import datetime, timezone
import csv
import random
import json
from bson import ObjectId
from metrics import calculate_metrics, detect_column_type
from dotenv import load_dotenv

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Load environment variables from .env file
load_dotenv()

# Ensure the uploads directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

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

def get_csv_content(file_path, document_ids):
    """Read CSV file and return rows for specified document IDs"""
    try:
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            return [row for row in reader if document_ids is None or row['document_id'] in document_ids]
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}, {file_path}, {reader}")
        return []

@app.route('/')
def index():
    return "Welcome to the Evaluation Web-Service!"

@app.route('/create_use_case.html')
def create_use_case_page():
    return render_template('create_use_case.html')

@app.route('/create_use_case', methods=['POST'])
def create_use_case():
    data = request.json
    name = data['name']
    success_criteria = data.get('success_criteria', '')
    db = get_db_connection()
    use_cases = db.use_cases
    use_cases.insert_one({'name': name, 'success_criteria': success_criteria, 'created_at': datetime.now(timezone.utc)})

    return jsonify({'message': 'Use case created successfully'}), 201

@app.route('/upload_label_file.html')
def upload_label_file_page():
    return render_template('upload_label_file.html')

@app.route('/upload_label_file', methods=['POST'])
def upload_label_file():
    file_path = None
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        if 'use_case_name' not in request.form:
            return jsonify({'error': 'No use case name provided'}), 400

        use_case_name = request.form['use_case_name']
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        # Validate file extension
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'Only CSV files are allowed'}), 400

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        db = get_db_connection()
        use_cases = db.use_cases
        use_case = use_cases.find_one({'name': use_case_name})

        if not use_case:
            os.remove(file_path)
            return jsonify({'error': 'Use case not found'}), 404

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
            return jsonify({'error': str(ve)}), 400

        # Detect column types
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            
            # Detect column types
            column_types = {}
            for field in reader.fieldnames:
                if field not in ['document_id', 'row_id']:
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

        return jsonify({
            'message': 'Label file uploaded and processed successfully',
            'file_id': str(label_file_id),
            'golden_set_size': len(golden_set),
            'test_set_size': len(test_set)
        }), 201

    except Exception as e:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': str(e)}), 500

@app.route('/generate_report/<int:evaluation_iteration_id>', methods=['GET'])
def generate_report(evaluation_iteration_id):
    db = get_db_connection()
    evaluation_iterations = db.evaluation_iterations

    evaluation_iteration = evaluation_iterations.find_one({'_id': evaluation_iteration_id})
    if not evaluation_iteration:
        return jsonify({'message': 'Evaluation iteration not found'}), 404

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

    return jsonify(report)

@app.route('/view_report/<int:evaluation_iteration_id>')
def view_report(evaluation_iteration_id):
    return render_template('view_report.html', evaluation_iteration_id=evaluation_iteration_id)

@app.route('/use_case/<use_case_name>')
def view_use_case(use_case_name):
    """Display use case details and associated label files"""
    try:
        db = get_db_connection()
        
        # Find the use case - use _id for partitioning
        use_case = db.use_cases.find_one({
            'name': use_case_name
        })
        if not use_case:
            return render_template('error.html', message='Use case not found'), 404

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
                test_set_content = get_csv_content(file['file_path'], eval_set['test_set'])
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

        return render_template(
            'view_use_case.html',
            use_case=use_case,
            label_files=associated_files,
            evaluations=evaluations
        )

    except Exception as e:
        return render_template('error.html', message=str(e)), 500

# Add this route to list all use cases
@app.route('/use_cases')
def list_use_cases():
    """Display list of all use cases"""
    try:
        db = get_db_connection()
        use_cases = db.use_cases
        all_use_cases = list(use_cases.find().sort('created_at', -1))
        return render_template('use_cases.html', use_cases=all_use_cases)
    except Exception as e:
        return render_template('error.html', message=str(e)), 500

@app.route('/upload_extraction_result/<use_case_name>', methods=['POST'])
def upload_extraction_result(use_case_name):
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        if not file.filename.endswith('.json'):
            return jsonify({'error': 'Only JSON files are allowed'}), 400
            
        # Load and validate JSON content
        try:
            file_content = file.read()
            file.seek(0)  # Reset file pointer
            extraction_results = json.loads(file_content.decode('utf-8'))
            if not isinstance(extraction_results, list):
                return jsonify({'error': 'JSON must contain an array of results'}), 400

            # Validate required fields in each result
            required_fields = {'document_id'}  # Add any other required fields
            for result in extraction_results:
                if not isinstance(result, dict):
                    return jsonify({'error': 'Each result must be an object'}), 400
                if not all(field in result for field in required_fields):
                    return jsonify({'error': f'Missing required fields: {required_fields}'}), 400
                
        except json.JSONDecodeError as e:
            return jsonify({'error': f'Invalid JSON format: {str(e)}'}), 400
            
        db = get_db_connection()
        
        # Find use case
        use_case = db.use_cases.find_one({'name': use_case_name})
        if not use_case:
            return jsonify({'error': 'Use case not found'}), 404
            
        # Find latest evaluation set for the use case
        latest_eval_set = db.evaluation_sets.find_one(
            {'use_case_id': use_case['_id']},
            sort=[('created_at', -1)]
        )
        
        if not latest_eval_set:
            return jsonify({'error': 'No evaluation set found for this use case'}), 404
            
        # Get label file content
        label_file = db.label_files.find_one({'_id': latest_eval_set['label_file_id']})
        if not label_file:
            return jsonify({'error': 'Label file not found'}), 404
        
        print(label_file['file_path'])
            
        # Read label file content
        label_data = get_csv_content(label_file['file_path'], None)  # Get all rows
        
        # Validate document IDs match
        label_doc_ids = set(row['document_id'] for row in label_data)
        result_doc_ids = set(row['document_id'] for row in extraction_results)
        print(extraction_results)


        if not result_doc_ids.issubset(label_doc_ids):
            return jsonify(
                {'error': f'Document IDs in extraction results do not match label file, {result_doc_ids.difference(label_doc_ids)} are missing in label set'}
                ), 400
            
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
            label_data,
            extraction_results,
            latest_eval_set['test_set']
        )
        
        golden_set_metrics = calculate_metrics(
            label_data,
            extraction_results,
            latest_eval_set['gold_set']
        )
        
        total_metrics = calculate_metrics(
            label_data,
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
        
        return jsonify({
            'message': 'Extraction results uploaded and evaluated successfully',
            'evaluation_iteration_id': str(iteration_id),
            'metrics_summary': {
                'test_set': test_set_metrics,
                'golden_set': golden_set_metrics,
                'total': total_metrics
            }
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/evaluation/<evaluation_iteration_id>')
def view_evaluation(evaluation_iteration_id):
    try:
        db = get_db_connection()
        
        # Find evaluation iteration
        evaluation = db.evaluation_iterations.find_one({'_id': ObjectId(evaluation_iteration_id)})
        if not evaluation:
            return render_template('error.html', message='Evaluation not found'), 404
            
        # Get related data
        use_case = db.use_cases.find_one({'_id': evaluation['use_case_id']})
        label_file = db.label_files.find_one({'_id': evaluation['label_file_id']})
        extraction_result = db.extraction_results.find_one({'_id': evaluation['extraction_result_id']})
        
        # Get test set content for comparison
        eval_set = db.evaluation_sets.find_one({'label_file_id': label_file['_id']})
        test_set_labels = get_csv_content(label_file['file_path'], eval_set['test_set'])
        test_set_results = [r for r in extraction_result['results'] 
                           if r['document_id'] in eval_set['test_set']]
        
        return render_template(
            'view_evaluation.html',
            evaluation=evaluation,
            use_case=use_case,
            label_file=label_file,
            test_set_labels=test_set_labels,
            test_set_results=test_set_results
        )
        
    except Exception as e:
        return render_template('error.html', message=str(e)), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
