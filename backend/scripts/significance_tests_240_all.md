# Paired significance tests (240-query leave-one-edge-out, multi-method run)

Input artifact: `scripts\evaluation_report_data1_leave_one_edge_out_240_all.json`  
n_queries=240, alpha=0.05, bootstrap_resamples=10000, test=wilcoxon_signed_rank_normal_approx_tie_corrected

| Metric | A vs B | mean(A) | mean(B) | mean diff | 95% CI | z | p-value | effect r | Significant? |
|---|---|---|---|---|---|---|---|---|---|
| ndcg_at_5 | hybrid vs pgpr_only | 0.7438 | 0.7441 | -0.0003 | [-0.0176, 0.0177] | -0.044 | 0.9652 | -0.012 | No |
| ndcg_at_5 | hybrid vs graph_heuristic | 0.7438 | 0.7438 | 0.0000 | [-0.0186, 0.0193] | -0.168 | 0.8665 | -0.043 | No |
| ndcg_at_5 | hybrid vs random | 0.7438 | 0.7025 | 0.0414 | [0.0124, 0.0709] | -2.915 | 0.003562 | 0.422 | Yes |
| ndcg_at_5 | pgpr_only vs graph_heuristic | 0.7441 | 0.7438 | 0.0003 | [-0.0099, 0.0106] | -0.104 | 0.9175 | -0.029 | No |
| mrr | hybrid vs pgpr_only | 0.7657 | 0.7641 | 0.0017 | [-0.0150, 0.0186] | -0.256 | 0.7977 | 0.075 | No |
| mrr | hybrid vs graph_heuristic | 0.7657 | 0.7645 | 0.0012 | [-0.0190, 0.0219] | -0.211 | 0.8325 | 0.051 | No |
| mrr | hybrid vs random | 0.7657 | 0.7249 | 0.0408 | [0.0063, 0.0760] | -2.337 | 0.01945 | 0.372 | Yes |
| mrr | pgpr_only vs graph_heuristic | 0.7641 | 0.7645 | -0.0005 | [-0.0155, 0.0137] | -0.119 | 0.9056 | 0.033 | No |
| precision_at_5 | hybrid vs pgpr_only | 0.6656 | 0.6608 | 0.0049 | [-0.0159, 0.0258] | -0.638 | 0.5232 | 0.113 | No |
| precision_at_5 | hybrid vs graph_heuristic | 0.6656 | 0.6626 | 0.0031 | [-0.0193, 0.0253] | -0.502 | 0.6159 | 0.088 | No |
| precision_at_5 | hybrid vs random | 0.6656 | 0.6677 | -0.0021 | [-0.0247, 0.0196] | -0.428 | 0.6686 | -0.064 | No |
| precision_at_5 | pgpr_only vs graph_heuristic | 0.6608 | 0.6626 | -0.0018 | [-0.0165, 0.0128] | -0.182 | 0.8559 | -0.034 | No |
| recall_at_5 | hybrid vs pgpr_only | 0.7458 | 0.7472 | -0.0014 | [-0.0222, 0.0194] | -0.126 | 0.8995 | -0.038 | No |
| recall_at_5 | hybrid vs graph_heuristic | 0.7458 | 0.7465 | -0.0007 | [-0.0201, 0.0194] | -0.234 | 0.8147 | -0.066 | No |
| recall_at_5 | hybrid vs random | 0.7458 | 0.7354 | 0.0104 | [-0.0153, 0.0382] | -1.154 | 0.2485 | 0.219 | No |
| recall_at_5 | pgpr_only vs graph_heuristic | 0.7472 | 0.7465 | 0.0007 | [-0.0111, 0.0125] | -0.091 | 0.9278 | -0.030 | No |
| explanation_coverage | hybrid vs pgpr_only | 0.8667 | 0.8542 | 0.0125 | [-0.0083, 0.0333] | -1.134 | 0.2568 | 0.429 | No |
| explanation_coverage | hybrid vs graph_heuristic | 0.8667 | 0.8583 | 0.0083 | [-0.0125, 0.0292] | -0.816 | 0.4142 | 0.333 | No |
| explanation_coverage | hybrid vs random | 0.8667 | 0.8708 | -0.0042 | [-0.0292, 0.0208] | -0.333 | 0.7389 | -0.111 | No |
| explanation_coverage | pgpr_only vs graph_heuristic | 0.8542 | 0.8583 | -0.0042 | [-0.0208, 0.0083] | -0.577 | 0.5637 | -0.333 | No |
| cold_start_success | hybrid vs pgpr_only | 0.8167 | 0.8125 | 0.0042 | [-0.0167, 0.0250] | -0.378 | 0.7055 | 0.143 | No |
| cold_start_success | hybrid vs graph_heuristic | 0.8167 | 0.8208 | -0.0042 | [-0.0292, 0.0208] | -0.302 | 0.763 | -0.091 | No |
| cold_start_success | hybrid vs random | 0.8167 | 0.8333 | -0.0167 | [-0.0542, 0.0208] | -0.853 | 0.3938 | -0.182 | No |
| cold_start_success | pgpr_only vs graph_heuristic | 0.8125 | 0.8208 | -0.0083 | [-0.0333, 0.0167] | -0.707 | 0.4795 | -0.250 | No |
