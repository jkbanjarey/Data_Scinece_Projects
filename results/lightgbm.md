# LightGBM (Phase 3)

Time-based train/validation/test evaluation. The validation period is used only for early stopping.

   model stage split  best_iteration pr_auc base_rate precision@5% recall@5% lift@5%     n
lightgbm     A   val             201  0.220     0.104        0.356     0.172   3.430 12794
lightgbm     A  test             201  0.180     0.096        0.272     0.141   2.828 12448
lightgbm     B   val             179  0.243     0.104        0.361     0.174   3.475 12794
lightgbm     B  test             179  0.255     0.096        0.395     0.206   4.116 12448

The Stage-B test outreach queue contains the highest-risk 5% of orders and contribution-based reason tags.
