# Balance reconciliation run — Andina Telecom (synthetic)

- **subscribers**: 20000
- **days**: 30
- **source_rows_events**: 557276
- **subscriber_days_reconciled**: 600000
- **flagged_subscriber_days**: 1795
- **micro_fraud_found**: 50/50
- **micro_fraud_false_positives**: 0
- **micro_fraud_total_loss**: 30.24
- **recharge_not_credited_found**: 179/180
- **duplicated_transfer_logs_found**: 58/58
- **unexplained**: 0
- **seconds_generate**: 4.1
- **seconds_extract_transform**: 5.4
- **seconds_load_reconcile**: 7.0

## Top micro-fraud suspects
| msisdn   |   days_hit |   median_cents |   total_loss |   share_of_days |
|:---------|-----------:|---------------:|-------------:|----------------:|
| S0000084 |         30 |              2 |         0.67 |               1 |
| S0019921 |         30 |              2 |         0.67 |               1 |
| S0001557 |         30 |              2 |         0.66 |               1 |
| S0002220 |         30 |              2 |         0.66 |               1 |
| S0012658 |         30 |              2 |         0.66 |               1 |
| S0006190 |         30 |              2 |         0.65 |               1 |
| S0008030 |         30 |              2 |         0.65 |               1 |
| S0002350 |         30 |              2 |         0.64 |               1 |
| S0002601 |         30 |              2 |         0.64 |               1 |
| S0016749 |         30 |              2 |         0.64 |               1 |

## Deviation reasons
| reason                           |   subscriber_days |
|:---------------------------------|------------------:|
| recharge_not_credited            |               179 |
| transfer_log_duplicated_receiver |                58 |
| transfer_log_duplicated_donor    |                58 |
