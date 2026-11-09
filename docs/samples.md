# Sample responses

## 01-normal

Query: `Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. I prefer highly rated restaurants.`

Faults: none

| Field | Value |
| --- | --- |
| intent | discovery |
| dish | biryani |
| cuisine | not specified |
| ingredients | not specified |
| diet | veg |
| max_price_inr | 300 |
| max_eta_min | 30 |
| min_rating | not specified |
| rating_preference | high |
| price_preference | not specified |
| speed_preference | not specified |
| location | not specified |
| other_preferences | not specified |
| parser | rules |

Pick: Subz Dum Biryani at Lucknowi Degh via Bitebox

Summary: Recommended because it matches your vegetarian requirement, stays within your ₹300 budget at ₹235 after the offer, has a 4.8 rating from 950 ratings, and has an estimated delivery time of 22 minutes.

Reasons:

- Vegetarian (marked veg by Bitebox)
- Subz Dum Biryani matches “biryani”
- ₹285, ₹235 after 20% off (max ₹50) — within your ₹300 budget
- 22 min delivery — inside your 30-minute limit
- Rated 4.8 from 950 ratings — the highest rating among options that fit

Warnings:

none

## 02-missing-info

Query: `suggest a biryani`

Faults: none

| Field | Value |
| --- | --- |
| intent | discovery |
| dish | biryani |
| cuisine | not specified |
| ingredients | not specified |
| diet | not specified |
| max_price_inr | not specified |
| max_eta_min | not specified |
| min_rating | not specified |
| rating_preference | not specified |
| price_preference | not specified |
| speed_preference | not specified |
| location | not specified |
| other_preferences | not specified |
| parser | rules |

Pick: Subz Dum Biryani at Lucknowi Degh via Bitebox

Summary: Recommended because it has a 4.8 rating from 950 ratings, costs ₹235, and has an estimated delivery time of 22 minutes.

Reasons:

- Subz Dum Biryani matches “biryani”
- Rated 4.8 from 950 ratings — the highest rating among options that fit

Warnings:

none

## 03-provider-timeout

Query: `Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. I prefer highly rated restaurants.`

Faults: tiffinly=timeout

| Field | Value |
| --- | --- |
| intent | discovery |
| dish | biryani |
| cuisine | not specified |
| ingredients | not specified |
| diet | veg |
| max_price_inr | 300 |
| max_eta_min | 30 |
| min_rating | not specified |
| rating_preference | high |
| price_preference | not specified |
| speed_preference | not specified |
| location | not specified |
| other_preferences | not specified |
| parser | rules |

Pick: Subz Dum Biryani at Lucknowi Degh via Bitebox

Summary: Recommended because it matches your vegetarian requirement, stays within your ₹300 budget at ₹235 after the offer, has a 4.8 rating from 950 ratings, and has an estimated delivery time of 22 minutes.

Reasons:

- Vegetarian (marked veg by Bitebox)
- Subz Dum Biryani matches “biryani”
- ₹285, ₹235 after 20% off (max ₹50) — within your ₹300 budget
- 22 min delivery — inside your 30-minute limit
- Rated 4.8 from 950 ratings — the highest rating among options that fit

Warnings:

- Tiffinly didn't respond within 1.5 s, so its listings weren't compared.

## 04-incomplete-data

Query: `Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. I prefer highly rated restaurants.`

Faults: bitebox=partial

| Field | Value |
| --- | --- |
| intent | discovery |
| dish | biryani |
| cuisine | not specified |
| ingredients | not specified |
| diet | veg |
| max_price_inr | 300 |
| max_eta_min | 30 |
| min_rating | not specified |
| rating_preference | high |
| price_preference | not specified |
| speed_preference | not specified |
| location | not specified |
| other_preferences | not specified |
| parser | rules |

Pick: Veg Dum Biryani (Serves 1) at Dum Pukht House via Tiffinly

Summary: Recommended because it matches your vegetarian requirement, stays within your ₹300 budget at ₹229 after the offer, has a 4.6 rating from 1,800 ratings, and has an estimated delivery time of 20–30 minutes.

Reasons:

- Vegetarian (marked veg by Tiffinly)
- Veg Dum Biryani (Serves 1) matches “biryani”
- ₹279, ₹229 after ₹50 off — within your ₹300 budget
- 20–30 min delivery — inside your 30-minute limit
- Rated 4.6 from 1,800 ratings — the highest rating among options that fit

Warnings:

none

## 05-preferences

Query: `Jain thali in Dadar under ₹300`

Faults: none

| Field | Value |
| --- | --- |
| intent | discovery |
| dish | thali |
| cuisine | not specified |
| ingredients | not specified |
| diet | veg |
| max_price_inr | 300 |
| max_eta_min | not specified |
| min_rating | not specified |
| rating_preference | not specified |
| price_preference | not specified |
| speed_preference | not specified |
| location | Dadar |
| other_preferences | jain |
| parser | rules |

Pick: Jain Thali at Thali Ghar via Tiffinly

Summary: Recommended because it matches your vegetarian requirement, is in Dadar, stays within your ₹300 budget at ₹260, has a 4.4 rating from 980 ratings, and has an estimated delivery time of 30–40 minutes.

Reasons:

- Vegetarian (marked veg by Tiffinly)
- Jain Thali matches “thali”
- ₹260 — within your ₹300 budget
- Rated 4.4 from 980 ratings
- In Dadar, as requested
- Matches “jain”

Warnings:

none

## 06-cheap-and-fast

Query: `cheap veg momos in Powai asap`

Faults: none

| Field | Value |
| --- | --- |
| intent | discovery |
| dish | momos |
| cuisine | not specified |
| ingredients | not specified |
| diet | veg |
| max_price_inr | not specified |
| max_eta_min | not specified |
| min_rating | not specified |
| rating_preference | not specified |
| price_preference | low |
| speed_preference | fast |
| location | Powai |
| other_preferences | not specified |
| parser | rules |

Pick: Veg Steamed Momos at Momo Mia via Bitebox

Summary: Recommended because it matches your vegetarian requirement, is in Powai, has a 4.3 rating from 870 ratings, costs ₹119, and has an estimated delivery time of 18 minutes.

Reasons:

- Vegetarian (marked veg by Bitebox)
- Veg Steamed Momos matches “momos”
- Rated 4.3 from 870 ratings — the highest rating among options that fit
- In Powai, as requested

Warnings:

none

## 07-clarification

Query: `within 45`

Faults: none

| Field | Value |
| --- | --- |
| intent | clarification |
| dish | not specified |
| cuisine | not specified |
| ingredients | not specified |
| diet | not specified |
| max_price_inr | not specified |
| max_eta_min | not specified |
| min_rating | not specified |
| rating_preference | not specified |
| price_preference | not specified |
| speed_preference | not specified |
| location | not specified |
| other_preferences | not specified |
| parser | rules |

Clarification: “within 45” has no unit (₹ or minutes?), so it was ignored. What would you like to eat? For example: “veg biryani under ₹300 in 30 minutes”.

Warnings:

none
