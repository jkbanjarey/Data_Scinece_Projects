# Baselines (Phase 2)

Time-based split: train 2017-01..2018-04, val 2018-05..06, test 2018-07..08.
Metrics computed on the stated split; ranking metrics are threshold-free.

       model stage split pr_auc base_rate precision@1% precision@5% precision@10% recall@1% recall@5% recall@10%     n
    majority     A   val  0.104     0.104        0.102        0.094         0.097     0.010     0.045      0.093 12794
    majority     A  test  0.096     0.096        0.113        0.095         0.092     0.012     0.049      0.096 12448
    majority     B   val  0.104     0.104        0.102        0.094         0.097     0.010     0.045      0.093 12794
    majority     B  test  0.096     0.096        0.113        0.095         0.092     0.012     0.049      0.096 12448
already-late     B   val  0.125     0.104        0.312        0.130         0.109     0.030     0.062      0.105 12794
already-late     B  test  0.177     0.096        0.677        0.240         0.161     0.070     0.125      0.168 12448
    logistic     A   val  0.200     0.104        0.453        0.306         0.246     0.044     0.147      0.236 12794
    logistic     A  test  0.163     0.096        0.379        0.256         0.184     0.039     0.133      0.191 12448
    logistic     B   val  0.218     0.104        0.461        0.336         0.269     0.044     0.162      0.259 12794
    logistic     B  test  0.204     0.096        0.468        0.338         0.249     0.048     0.176      0.259 12448

Notes:
- `majority` scores every order at the train-set prevalence; its PR-AUC equals the base rate by construction.
- `already-late` is the operational heuristic available at Stage B: rank by remaining margin at handoff.
- Logistic regression uses one-hot category/states + median-imputed, scaled numerics (class_weight=balanced).