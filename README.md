# CrossPay — Analytics Test Dataset

CrossPay is a **synthetic** international B2B payments service: companies use it
to pay contractors and vendors across borders. All data below is artificially
generated for this exercise — no real companies or people are represented.

**Data period:** 2025-01-01 — 2025-12-20.

## Files

### clients.csv
One row per client company.

| column | description |
|---|---|
| client_id | Client identifier (CLxxxx) |
| signup_date | Date the client registered |
| country | Client's country |
| segment | Business segment |
| acquisition_channel | How the client was acquired |
| account_manager_id | Assigned account manager (see managers.csv) |
| company_size | Small / Medium / Large / Enterprise |

### transactions.csv
One row per payment attempt.

| column | description |
|---|---|
| transaction_id | Payment identifier (TXxxxxxxxx) |
| client_id | Paying client |
| created_at | When the payment was initiated |
| completed_at | When funds were delivered (may be empty) |
| payout_country | Country of the payout recipient |
| currency | Transaction currency |
| amount | Payment amount **in the transaction currency** |
| status | completed / failed / refunded / pending |
| client_fee | Fee charged to the client, in the transaction currency |
| direct_cost | CrossPay's direct processing cost, in the transaction currency |
| failure_reason | Filled for failed payments only |

Statuses: `completed` — funds delivered; `failed` — attempt was not executed;
`refunded` — executed and subsequently returned; `pending` — still in progress.

### fx_rates.csv

| column | description |
|---|---|
| date | Quote date |
| currency | Currency code |
| usd_rate | **How many USD one unit of the currency is worth** (USD = 1) |

### support_tickets.csv

| column | description |
|---|---|
| ticket_id | Ticket identifier |
| client_id | Client who opened the ticket |
| opened_at | When the ticket was opened |
| resolved_at | When it was resolved (may be empty) |
| category | Payment issue / Documents / Compliance / Account / Technical / Other |
| priority | Low / Medium / High / Critical |

### managers.csv

| column | description |
|---|---|
| account_manager_id | Manager identifier (M01–M06) |
| start_date | First working day at CrossPay |
| region | Manager's home region |
