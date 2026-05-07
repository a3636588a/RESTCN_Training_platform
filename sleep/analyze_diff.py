
import os
import pandas as pd
import numpy as np
import json

base_dir = r"C:\Users\USE\Desktop\SEAN_CODE\CNN_station_breathe\sleep"
folders = [
    "260504_data_sean",
    "260504_data_clement",
    "260504_data_bruce",
    "260506_data_steven",
    "260506_data_randy"
]

labels_map = {
    "2": "Turn_left",
    "3": "Turn_right",
    "4": "Getout_of_bed",
    "5": "lying_down",
    "6": "Lying_left",
    "7": "Lying_right",
    "10": "Raising_right_foot",
    "11": "Raising_left_foot",
    "17": "Get_up"
}

results = []

for folder in folders:
    folder_path = os.path.join(base_dir, folder)
    if not os.path.isdir(folder_path):
        continue
    
    user_name = folder.split("_")[-1]
    print(f"Processing {user_name}...")
    
    for filename in os.listdir(folder_path):
        if not filename.endswith(".csv"):
            continue
        
        prefix = filename.split("-")[0]
        if prefix not in labels_map:
            continue
        
        label_name = labels_map[prefix]
        file_path = os.path.join(folder_path, filename)
        
        try:
            df = pd.read_csv(file_path)
            # Use only ROWCH1-6
            channels = [f"ROWCH{i}" for i in range(1, 7)]
            if not all(c in df.columns for c in channels):
                continue
                
            raw_data = df[channels].values
            
            # Basic stats per file
            mean_vals = np.mean(raw_data, axis=0)
            std_vals = np.std(raw_data, axis=0)
            range_vals = np.max(raw_data, axis=0) - np.min(raw_data, axis=0)
            
            results.append({
                "User": user_name,
                "Label": label_name,
                "Prefix": prefix,
                "Mean": mean_vals,
                "Std": std_vals,
                "Range": range_vals
            })
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

# Summarize
df_res = pd.DataFrame(results)

# Group by User and Label to get average stats
summary = df_res.groupby(["User", "Label"]).agg({
    "Mean": lambda x: np.mean(np.stack(x), axis=0),
    "Std": lambda x: np.mean(np.stack(x), axis=0),
    "Range": lambda x: np.mean(np.stack(x), axis=0)
}).reset_index()

# Export to JSON for easy reading
output_file = os.path.join(base_dir, "multi_person_analysis.json")
summary_list = summary.to_dict(orient="records")

# Convert numpy arrays to lists for JSON
for item in summary_list:
    item["Mean"] = item["Mean"].tolist()
    item["Std"] = item["Std"].tolist()
    item["Range"] = item["Range"].tolist()

with open(output_file, "w") as f:
    json.dump(summary_list, f, indent=2)

print(f"Analysis complete. Results saved to {output_file}")
