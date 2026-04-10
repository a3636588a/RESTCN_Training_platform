import tensorflow as tf
import numpy as np
import os
import sys

def export_cnn_weights(model_path, output_h):
    if not os.path.exists(model_path):
        print(f"Error: Model file {model_path} not found.")
        return False
    
    # Load model and disable name restrictions
    model = tf.keras.models.load_model(model_path, compile=False)
    print(f"Loading model from {model_path}...")
    model.summary()

    with open(output_h, 'w') as f:
        f.write("#ifndef CNN_WEIGHTS_H\n#define CNN_WEIGHTS_H\n\n")
        f.write("// Auto-generated weights for Dual-SE 2-Layer CNN Architecture\n\n")
        
        def write_array(name, arr):
            arr_flat = arr.flatten()
            f.write(f"const float {name}[{len(arr_flat)}] = {{\n    ")
            for i, x in enumerate(arr_flat):
                f.write(f"{x:.8f}f")
                if i < len(arr_flat) - 1:
                    f.write(", ")
                if (i + 1) % 8 == 0:
                    f.write("\n    ")
            f.write("\n};\n\n")

        # Sequentially identify and export layers
        conv_idx = 0      # Track Conv Layers (1, 2)
        dense_idx = 0     # General dense counter
        in_se_block = False
        se_step = 0

        all_layers = model.layers
        i = 0
        while i < len(all_layers):
            layer = all_layers[i]
            l_name = layer.name.lower()
            
            # 1. Conv1D logic (Handle BN Fusion)
            if isinstance(layer, tf.keras.layers.Conv1D):
                conv_idx += 1
                in_se_block = False # Reset SE context for new conv
                
                w, b = layer.get_weights()
                # Check for BN in next few layers
                bn_layer = None
                for search_idx in range(i+1, min(i+5, len(all_layers))):
                    if isinstance(all_layers[search_idx], tf.keras.layers.BatchNormalization):
                        bn_layer = all_layers[search_idx]
                        break
                
                if bn_layer:
                    print(f"Fusing BN ({bn_layer.name}) into Conv1D ({layer.name}) [CONV{conv_idx}]")
                    gamma, beta, mean, var = bn_layer.get_weights()
                    eps = bn_layer.epsilon
                    std = np.sqrt(var + eps)
                    scale = gamma / std
                    w_fused = w * scale
                    b_fused = (b - mean) * scale + beta
                    write_array(f"CONV{conv_idx}_W", w_fused)
                    write_array(f"CONV{conv_idx}_B", b_fused)
                else:
                    print(f"Exporting Conv1D ({layer.name}) [CONV{conv_idx}]")
                    write_array(f"CONV{conv_idx}_W", w)
                    write_array(f"CONV{conv_idx}_B", b)

            # 2. SE Block Detection (Logic: GAP1D -> Dense -> Dense)
            elif isinstance(layer, tf.keras.layers.GlobalAveragePooling1D):
                # Detect if this is the start of an SE block (vs GAP for waveform branch)
                # SE GAP usually has a Conv1D as input and is followed by Dense
                if i + 1 < len(all_layers) and isinstance(all_layers[i+1], tf.keras.layers.Dense):
                    in_se_block = True
                    se_step = 1
                    print(f"Entering SE Block for CONV{conv_idx}")

            # 3. Dense logic
            elif isinstance(layer, tf.keras.layers.Dense):
                w, b = layer.get_weights()
                out_dim = w.shape[1]
                
                # Case A: Inside SE Block
                if in_se_block:
                    if se_step == 1:
                        print(f"Exporting CONV{conv_idx}_SE_Squeeze (Dense {layer.name})")
                        write_array(f"CONV{conv_idx}_SE_SQ_W", w)
                        write_array(f"CONV{conv_idx}_SE_SQ_B", b)
                        se_step = 2
                    elif se_step == 2:
                        print(f"Exporting CONV{conv_idx}_SE_Excite (Dense {layer.name})")
                        write_array(f"CONV{conv_idx}_SE_EX_W", w)
                        write_array(f"CONV{conv_idx}_SE_EX_B", b)
                        in_se_block = False
                        se_step = 0
                
                # Case B: Branch or Final Layers
                else:
                    name_tag = f"DENSE_X{dense_idx}"
                    # Robust identification:
                    # 1. Variance branch: 1st dense with 32 units
                    # 2. Mean branch: 2nd dense with 32 units
                    # 3. Merger/Head: 128 units, then 64 units
                    if i == len(all_layers) - 1:
                        name_tag = "DENSE_OUT"
                    elif "variance" in l_name or (out_dim == 32 and dense_idx == 0):
                        name_tag = "DENSE_VAR"
                        dense_idx = 1 # Mark that we found one 32-unit branch
                    elif "mean" in l_name or (out_dim == 32 and dense_idx == 1):
                        name_tag = "DENSE_MEAN"
                        dense_idx = 2
                    elif out_dim == 128:
                        name_tag = "DENSE_F1"
                    elif out_dim == 64:
                        name_tag = "DENSE_F2"
                    else:
                        name_tag = f"DENSE_UNKN_{dense_idx}"
                        dense_idx += 1

                    print(f"Exporting {name_tag} ({layer.name}), out={out_dim}")
                    write_array(f"{name_tag}_W", w)
                    write_array(f"{name_tag}_B", b)

            i += 1
            
        f.write("#endif // CNN_WEIGHTS_H\n")

    
    print(f"Successfully exported weights to {output_h}")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 2:
        export_cnn_weights(sys.argv[1], sys.argv[2])
    else:
        # Default paths (will be overriden by UI)
        m_path = r'C:\Users\USE\Desktop\SEAN_CODE\station_TESTNN\TESTNN\plk\cnn.keras'
        o_path = r'C:\Users\USE\Desktop\SEAN_CODE\station_TESTNN\TESTNN\plk\cnnlib\cnn_weights.h'
        export_cnn_weights(m_path, o_path)
