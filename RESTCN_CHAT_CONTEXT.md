# RESTCN Chat Context

## Workspace
- Active workspace: `C:\Users\USE\Desktop\SEAN_CODE\RESTCN`
- Branch: `RESTCN`
- Source: cloned from local working tree of `CNN_station_breathe` (including uncommitted changes)

## What We Discussed
- Main topic: capacitor-sensor motion analysis productization strategy.
- Current pipeline understanding:
  - Train/tune on `ui_v6`
  - Export/generated C code and deploy to MCU (`mcu_cnn_v2` flow)
- Model discussion:
  - 1D-CNN is viable for product if consistency/process control is strong.
  - DS-CNN / DS-ResTCN / TCN were discussed as potential upgrades.
  - Priority recommendation was process stability first, model swap second.

## Key Technical Conclusions
- UI detect and MCU CNN pipeline are algorithmically aligned at core (`dn + slope`, CNN + postprocess).
- Practical mismatches usually come from configuration/runtime differences, not necessarily architecture differences.
- Your note clarified that parameters are generated from UI into C before deploy, so defaults seen in code are not always runtime truth.

## Dataset/Training Review Highlights
- Reviewed:
  - `sleep\data_all_select`
  - `sleep\訓練紀錄demo.txt`
- Observed risks for production stability:
  - class/file count imbalance
  - some abnormal sample lengths
  - validation strategy should emphasize subject/group split for real-world generalization

## Repo Operations Completed
- Copied full working tree from:
  - `C:\Users\USE\Desktop\SEAN_CODE\CNN_station_breathe`
  - to `C:\Users\USE\Desktop\SEAN_CODE\RESTCN`
- Verified `RESTCN` is a valid git repo with same origin history.
- Created and switched branch:
  - `RESTCN`

## Suggested Next Step (if you want)
1. In this `RESTCN` branch, build a reproducible parity checklist for `ui_v6 detect` vs `mcu_v2` (inputs, features, logits, stable outputs).
2. Add a lightweight dataset QC script to flag outlier sample lengths before training.
3. Run one fixed replay batch and store baseline metrics for future model comparisons.
