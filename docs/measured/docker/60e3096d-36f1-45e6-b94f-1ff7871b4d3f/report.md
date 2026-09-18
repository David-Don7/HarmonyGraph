# HarmonyGraph measured experiment

Synthetic fixture results are software checks, not research evidence.

| Variant | nDCG@10 | p95 ms |
|---|---:|---:|
| B1_absolute | 0.5726361401144232 | 116.73 |
| B2_intervals | 1.0 | 86.64 |
| B3_global_key | 0.6666666666666666 | 291.14 |
| B4_deterministic_local | 1.0 | 316.60 |
| B5_uniform_edit | 1.0 | 401.27 |
| B6_manual | 1.0 | 22.12 |
| proposed | 1.0 | 19.03 |
| without_uncertainty | 1.0 | 18.05 |
| without_local_changes | 0.6666666666666666 | 1178.10 |
| without_functions | 1.0 | 1096.59 |
| without_sections | 1.0 | 352.07 |
| without_boundaries | 1.0 | 282.61 |
| uniform_costs | 1.0 | 25.98 |
| without_quality | 1.0 | 933.27 |
| equal_weights | 1.0 | 422.30 |

```json
{
  "corpus_hash": "b78b18cfda87d09103999ce71c501c536518d0e8dfe7e7512f3355f846a66172",
  "benchmark_hash": "53f905adafc6f9944e210cccc9a8786b523241fc20ab25a54c35a5dc356ee0a0",
  "split_hash": "3da71882ec9d146eb4b2ffdb9a8d73c3462e4ff92c8ee949e3752fe2db933165",
  "configuration_hash": "cf909a770d3b35f2ff8963d81988fb68e173a0960bf90d603a24dfcf80aff8cf",
  "analysis_id": "5ea57feb-958c-4d31-a701-3c384f2908f2"
}
```
