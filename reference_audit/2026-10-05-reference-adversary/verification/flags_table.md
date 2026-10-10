Default parameters: {"min_models": 15, "top_k": 5, "min_top": 3, "tolerance": 1.0, "answer_rounding": "nearest", "zero_cluster_min_models": 15, "binary_outputs": "mismatch"}

Prototype parameters: {"min_models": 15, "top_k": 5, "min_top": 3, "tolerance": 1.0, "answer_rounding": "truncate", "zero_cluster_min_models": 15, "binary_outputs": "skip"}

Payload: `paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/data.json.gz` (sha256 `1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18`); 46 models; top 5: gpt-6-sol, claude-opus-5.5, gpt-5.6-sol, gpt-6-luna, claude-sonnet-5.5.

Default flags 61 of 1928 scored cells; the prototype flags 41.

| # | Cell | State | Reference | Cluster answer (models, of top 5) | Exact | Prototype | Covered by |
|---:|---|---|---:|---|---:|:---:|---|
| 1 | scenario_007 state_refundable_credits | ID | 155 | 0 (17, 0) | 10 | yes |  |
| 2 | scenario_013 snap | AZ | 240 | 0 (46, 5) | 0 | yes |  |
| 3 | scenario_013 state_refundable_credits | AZ | 25 | 0 (35, 4) | 10 | yes |  |
| 4 | scenario_014 state_income_tax_before_refundable_credits | WV | 3,092.19 | 3,255 (6, 3) | 0 | yes |  |
| 5 | scenario_018 state_income_tax_before_refundable_credits | AZ | 1,146.05 | 1,137 (12, 5) | 0 | yes |  |
| 6 | scenario_023 federal_income_tax_before_refundable_credits | CA | 643.43 | 0 (28, 4) | 5 | yes |  |
| 7 | scenario_023 state_income_tax_before_refundable_credits | CA | 12.78 | 0 (23, 0) | 1 | yes |  |
| 8 | scenario_023 state_refundable_credits | CA | 95.15 | 0 (19, 1) | 1 | yes |  |
| 9 | scenario_025 state_income_tax_before_refundable_credits | OH | 1,921.57 | 1,590 (8, 4) | 0 |  |  |
| 10 | scenario_026 child1_medicaid_eligible | NC | 1 | 0 (44, 5) | 1 |  |  |
| 11 | scenario_026 child2_medicaid_eligible | NC | 1 | 0 (44, 5) | 1 |  |  |
| 12 | scenario_026 child3_medicaid_eligible | NC | 1 | 0 (44, 5) | 1 |  |  |
| 13 | scenario_026 federal_refundable_credits | NC | 2,013.49 | 0 (20, 0); 2,059 (3, 3) | 7 | yes |  |
| 14 | scenario_027 snap | CT | 288 | 0 (38, 4) | 1 | yes |  |
| 15 | scenario_028 child1_chip_eligible | PA | 0 | 1 (19, 2) | 26 |  |  |
| 16 | scenario_028 child2_chip_eligible | PA | 0 | 1 (20, 2) | 25 |  |  |
| 17 | scenario_028 child3_chip_eligible | PA | 0 | 1 (19, 2) | 26 |  |  |
| 18 | scenario_028 payroll_tax | PA | 4,632 | 4,590 (31, 3) | 10 | yes | #194 (payroll, d972) |
| 19 | scenario_028 state_refundable_credits | PA | 62.41 | 0 (41, 3) | 3 | yes |  |
| 20 | scenario_029 head_medicaid_eligible | OK | 1 | 0 (19, 0) | 27 |  |  |
| 21 | scenario_029 state_refundable_credits | OK | 40 | 0 (44, 5) | 2 | yes |  |
| 22 | scenario_030 snap | TX | 288 | 0 (33, 2); 1,208 (3, 3) | 0 | yes |  |
| 23 | scenario_031 head_medicaid_eligible | CA | 1 | 0 (43, 4) | 3 |  | #197 (scenario_031 annotations) |
| 24 | scenario_032 free_school_meals_eligible | MN | 1 | 0 (23, 3) | 22 |  |  |
| 25 | scenario_032 payroll_tax | MN | 2,346.10 | 2,219 (33, 4) | 6 | yes | #194 (payroll, d972) |
| 26 | scenario_032 reduced_price_school_meals_eligible | MN | 0 | 1 (25, 3) | 20 |  |  |
| 27 | scenario_032 spouse_medicaid_eligible | MN | 1 | 0 (16, 1) | 29 |  |  |
| 28 | scenario_038 state_refundable_credits | LA | 365.80 | 0 (18, 0) | 10 | yes |  |
| 29 | scenario_039 head_medicare_eligible | VA | 0 | 1 (19, 1) | 27 |  |  |
| 30 | scenario_043 payroll_tax | CO | 330.73 | 313 (25, 1) | 16 | yes | #194 (payroll, d972) |
| 31 | scenario_043 state_refundable_credits | CO | 19 | 0 (39, 5) | 0 | yes |  |
| 32 | scenario_045 state_refundable_credits | MI | 760.79 | 0 (18, 0) | 4 | yes |  |
| 33 | scenario_051 state_income_tax_before_refundable_credits | LA | 820.35 | 830 (21, 5) | 0 | yes | #192 (Louisiana) |
| 34 | scenario_053 state_refundable_credits | ID | 155 | 0 (20, 0) | 7 | yes |  |
| 35 | scenario_054 head_wic_eligible | NC | 0 | 1 (16, 1) | 30 |  |  |
| 36 | scenario_054 snap | NC | 6,060 | 6,068 (6, 3) | 2 | yes |  |
| 37 | scenario_056 state_refundable_credits | NJ | 265.60 | 0 (34, 1) | 0 | yes |  |
| 38 | scenario_057 state_refundable_credits | LA | 33.20 | 0 (25, 1) | 15 | yes |  |
| 39 | scenario_066 state_refundable_credits | VA | 7.96 | 0 (25, 1) | 12 | yes |  |
| 40 | scenario_073 snap | MI | 288 | 0 (37, 5) | 3 | yes |  |
| 41 | scenario_075 head_medicare_eligible | FL | 0 | 1 (15, 1) | 31 |  |  |
| 42 | scenario_076 state_refundable_credits | ID | 465 | 0 (18, 0) | 7 | yes |  |
| 43 | scenario_077 state_income_tax_before_refundable_credits | LA | 305.14 | 315 (19, 5) | 0 | yes | #192 (Louisiana) |
| 44 | scenario_079 snap | AZ | 2,376 | 1,956 (3, 3) | 0 | yes |  |
| 45 | scenario_079 state_refundable_credits | AZ | 50 | 0 (38, 5) | 7 | yes |  |
| 46 | scenario_081 payroll_tax | MA | 14,192.66 | 13,388 (9, 3) | 9 |  | #194 (payroll, d972) |
| 47 | scenario_082 payroll_tax | NY | 8,108.03 | 7,665 (14, 3) | 4 | yes | #194 (payroll, d972) |
| 48 | scenario_082 state_refundable_credits | NY | 667 | 0 (18, 1) | 0 | yes |  |
| 49 | scenario_085 state_income_tax_before_refundable_credits | PA | 0 | 51 (27, 3) | 12 | yes |  |
| 50 | scenario_099 free_school_meals_eligible | CA | 1 | 0 (37, 3) | 8 |  |  |
| 51 | scenario_100 tanf | MT | 6,064.96 | 0 (24, 1) | 0 | yes |  |
| 52 | scenario_108 snap | WI | 288 | 0 (36, 4) | 3 | yes |  |
| 53 | scenario_112 federal_refundable_credits | TX | 453.10 | 0 (15, 0) | 25 | yes |  |
| 54 | scenario_115 state_income_tax_before_refundable_credits | AL | 4.68 | 0 (45, 5) | 1 | yes |  |
| 55 | scenario_118 state_refundable_credits | NY | 375 | 0 (24, 0) | 12 | yes |  |
| 56 | scenario_119 child1_chip_eligible | VA | 0 | 1 (15, 3) | 29 |  |  |
| 57 | scenario_119 child2_chip_eligible | VA | 0 | 1 (15, 3) | 29 |  |  |
| 58 | scenario_121 head_medicare_eligible | SC | 0 | 1 (16, 2) | 30 |  |  |
| 59 | scenario_121 snap | SC | 0 | 3,576 (9, 4) | 16 | yes |  |
| 60 | scenario_123 payroll_tax | PA | 11,194 | 11,093 (22, 3) | 11 | yes | #194 (payroll, d972) |
| 61 | scenario_123 state_income_tax_before_refundable_credits | PA | 3,070.06 | 4,452 (32, 5) | 0 | yes |  |
