from datetime import datetime

def calculate_metrics(actual_data, predicted_data, document_ids):
    """Calculate precision, recall, and accuracy for each field"""
    metrics = {}
    
    if not actual_data or not predicted_data:
        return metrics
        
    # Get all fields except document_id and row_id
    excluded_fields = {'document_id', 'row_id'}  # Explicitly exclude row_id
    fields = [field for field in actual_data[0].keys() if field not in excluded_fields]
    
    for field in fields:
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        
        for doc_id in document_ids:
            actual = next((row[field] for row in actual_data if row['document_id'] == doc_id), None)
            predicted = next((row.get(field) for row in predicted_data if row['document_id'] == doc_id), None)
            if field == 'Officer Age':
                print(actual, predicted, type(actual), type(predicted))
            
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
    """Detect the type of a column based on its values."""
    # Remove None and empty values
    non_empty_values = [v for v in values if v is not None and v != '']
    if not non_empty_values:
        return 'string'  # Default to string for empty columns
        
    # Try integer first
    try:
        all(int(v) for v in non_empty_values)
        return 'integer'
    except ValueError:
        pass
        
    # Try float next
    try:
        all(float(v) for v in non_empty_values)
        return 'float'
    except ValueError:
        pass
        
    # Check for boolean
    bool_values = {'true', 'false', 'yes', 'no', '1', '0', 'y', 'n'}
    if all(str(v).lower() in bool_values for v in non_empty_values):
        return 'boolean'
        
    # Default to string
    return 'string' 