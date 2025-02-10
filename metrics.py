from datetime import datetime

def calculate_metrics(actual_data, predicted_data, document_ids):
    """Calculate precision, recall, and accuracy for each field"""
    metrics = {}
    
    if not actual_data or not predicted_data:
        return metrics
        
    # Get all fields except document_id and row_id
    excluded_fields = {'document_id', 'row_id'}
    fields = [field for field in actual_data[0].keys() if field not in excluded_fields]
    
    for field in fields:
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        
        for doc_id in document_ids:
            actual = next((row[field] for row in actual_data if row['document_id'] == doc_id), None)
            predicted = next((row.get(field) for row in predicted_data if row['document_id'] == doc_id), None)
            
            if actual and predicted:
                if actual == predicted:
                    true_positives += 1
                else:
                    false_positives += 1
            elif predicted:
                false_positives += 1
            elif actual:
                false_negatives += 1
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        metrics[field] = {
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'true_positives': true_positives,
            'false_positives': false_positives,
            'false_negatives': false_negatives
        }
    
    return metrics 

def detect_column_type(values):
    """Detect the type of a column based on its values"""
    # Remove None and empty values
    values = [v for v in values if v and v.strip()]
    if not values:
        return 'string'
    
    # Try integer
    try:
        all(int(v) for v in values)
        return 'integer'
    except ValueError:
        pass
    
    # Try float
    try:
        all(float(v) for v in values)
        return 'float'
    except ValueError:
        pass
    
    # Try datetime
    date_formats = [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S'
    ]
    
    for date_format in date_formats:
        try:
            all(datetime.strptime(v, date_format) for v in values)
            return 'datetime'
        except ValueError:
            continue
    
    return 'string' 