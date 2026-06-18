import os
import csv
import tempfile

def update_csv_files(directory):
    target_cols = ['HOLDAVG1', 'HOLDAVG2', 'HOLDAVG3', 'HOLDAVG4', 'HOLDAVG5']
    new_values = ['16941', '18938', '18921', '19132', '16512']
    
    # Map column name to its new target value
    val_map = dict(zip(target_cols, new_values))
    
    csv_files = [f for f in os.listdir(directory) if f.lower().endswith('.csv')]
    print(f"Found {len(csv_files)} CSV files to process.")
    
    success_count = 0
    error_count = 0
    
    for filename in csv_files:
        # Avoid processing any temp files or the script itself
        if filename.startswith('~') or filename.startswith('temp'):
            continue
            
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    print(f"Skipping empty file: {filename}")
                    continue
                
                # Map column header to index
                col_indices = {}
                for col in target_cols:
                    if col in header:
                        col_indices[col] = header.index(col)
                
                if not col_indices:
                    # If columns are not found in this CSV, skip it silently or print info
                    continue
                
                rows = []
                for row in reader:
                    # Make sure the row has enough columns
                    for col, idx in col_indices.items():
                        if idx < len(row):
                            row[idx] = val_map[col]
                    rows.append(row)
            
            # Write modified content to a temporary file
            temp_fd, temp_path = tempfile.mkstemp(dir=directory, suffix='.tmp')
            try:
                with os.fdopen(temp_fd, 'w', newline='', encoding='utf-8') as temp_f:
                    writer = csv.writer(temp_f)
                    writer.writerow(header)
                    writer.writerows(rows)
                # Atomic replace on same drive
                os.replace(temp_path, filepath)
                success_count += 1
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            error_count += 1
            
    print(f"Processing finished. Successfully updated: {success_count}, Errors: {error_count}")

if __name__ == '__main__':
    # Run in the current directory where the CSV files are located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    update_csv_files(current_dir)
