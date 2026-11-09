# Parser evaluation

| parser/set | cases | field accuracy | exact match | invented | missed | wrong |
|---|---|---|---|---|---|---|
| rules/core | 20 | 1.000 | 1.000 (20/20) | 0 | 0 | 0 |
| rules/paraphrase | 5 | 0.954 | 0.400 (2/5) | 0 | 3 | 0 |
| llm/core | not run | | | | | |
| llm/paraphrase | not run | | | | | |

## Per-field accuracy

| field | rules/core | rules/paraphrase | llm/core | llm/paraphrase |
|---|---|---|---|---|
| intent | 1.00 | 1.00 |  |  |
| dish | 1.00 | 1.00 |  |  |
| cuisine | 1.00 | 1.00 |  |  |
| diet | 1.00 | 0.60 |  |  |
| ingredients | 1.00 | 1.00 |  |  |
| max_price_inr | 1.00 | 1.00 |  |  |
| max_eta_min | 1.00 | 1.00 |  |  |
| min_rating | 1.00 | 1.00 |  |  |
| rating_preference | 1.00 | 0.80 |  |  |
| price_preference | 1.00 | 1.00 |  |  |
| speed_preference | 1.00 | 1.00 |  |  |
| location | 1.00 | 1.00 |  |  |
| other_preferences | 1.00 | 1.00 |  |  |

## Failures

### rules/core

none

### rules/paraphrase

- `nothing with meat please, I'm in Powai and starving` — diet (missed): expected veg, got null
- `something Hyderabadi that's well reviewed` — rating_preference (missed): expected high, got null
- `plant-based bowl for under 250` — diet (missed): expected vegan, got null
