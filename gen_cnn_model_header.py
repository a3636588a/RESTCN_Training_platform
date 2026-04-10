import tensorflow as tf
import numpy as np
import os

def export_cnn_to_c(model_path, output_c_path):
    print(f"Loading model from {model_path}...")
    model = tf.keras.models.load_model(model_path)
    
    with open(output_c_path, 'w') as f:
        f.write('#include "cnn_model_data.h"\n\n')
        
        # Helper to write 1D arrays
        def write_array(name, data):
            f.write(f"const float {name}[{len(data)}] = {{\n    ")
            flat = data.flatten()
            for i, val in enumerate(flat):
                f.write(f"{val:.10f}f")
                if i < len(flat) - 1:
                    f.write(", ")
                if (i + 1) % 8 == 0:
                    f.write("\n    ")
            f.write("\n};\n\n")

        # Layer mapping and weight extraction
        # Current Architecture:
        # 1. Conv1D (16, k3) -> BatchNorm -> ReLU
        # 2. MaxPool2D (2)
        # 3. Conv1D (32, k3) -> BatchNorm -> ReLU
        # 4. GlobalAvgPool
        # 5. Dense (32) -> ReLU
        # 6. Dense (15) -> Softmax
        
        layers = model.layers
        
        # --- Conv1 + BN ---
        c1 = [l for l in layers if 'conv1d' in l.name][0]
        bn1 = [l for l in layers if 'batch_normalization' in l.name][0]
        
        W1 = c1.get_weights()[0] # (K, C_in, C_out) = (3, 10, 16)
        B1 = c1.get_weights()[1] if len(c1.get_weights()) > 1 else np.zeros(W1.shape[-1])
        
        gamma1, beta1, mean1, var1 = bn1.get_weights()
        eps = 1e-3
        scale1 = gamma1 / np.sqrt(var1 + eps)
        
        W1_fused = W1 * scale1
        B1_fused = (B1 - mean1) * scale1 + beta1
        
        write_array("conv1_W", W1_fused)
        write_array("conv1_B", B1_fused)
        
        # --- Conv2 + BN ---
        c2 = [l for l in layers if 'conv1d' in l.name][1]
        bn2 = [l for l in layers if 'batch_normalization' in l.name][1]
        
        W2 = c2.get_weights()[0] # (3, 16, 32)
        B2 = c2.get_weights()[1] if len(c2.get_weights()) > 1 else np.zeros(W2.shape[-1])
        
        gamma2, beta2, mean2, var2 = bn2.get_weights()
        scale2 = gamma2 / np.sqrt(var2 + eps)
        
        W2_fused = W2 * scale2
        B2_fused = (B2 - mean2) * scale2 + beta2
        
        write_array("conv2_W", W2_fused)
        write_array("conv2_B", B2_fused)
        
        # --- Dense 1 ---
        d1 = [l for l in layers if 'dense' in l.name][0]
        Wd1, Bd1 = d1.get_weights() # (37, 32)
        write_array("dense1_W", Wd1)
        write_array("dense1_B", Bd1)
        
        # --- Dense 2 ---
        d2 = [l for l in layers if 'dense' in l.name][1]
        Wd2, Bd2 = d2.get_weights() # (32, 15)
        write_array("dense2_W", Wd2)
        write_array("dense2_B", Bd2)

    print(f"Exported to {output_c_path} successfully.")

if __name__ == "__main__":
    # Update these paths to match your local setup
    MODEL_FILE = r"c:\Users\USE\Desktop\SEAN_CODE\station_TESTNN\TESTNN\plk\gesture_model_v5.keras"
    OUTPUT_FILE = r"c:\Users\USE\Desktop\SEAN_CODE\station_TESTNN\cnn_mcu\sil_ultra_slow_jogging - 20260130-Ver03.000\sil_ultra_slow_jogging - 20260130-Ver03.000\sil_all\cnn_lib\cnn_model_data.c"
    
    if os.path.exists(MODEL_FILE):
        export_cnn_to_c(MODEL_FILE, OUTPUT_FILE)
    else:
        print(f"Model file not found: {MODEL_FILE}. Please update gen_cnn_model_header.py with your .keras path.")
