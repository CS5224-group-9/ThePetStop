# Pet owner requirements survey — draft for D2

**Purpose:** understand how Singapore pet owners shop for pet supplies and what would make a multi-shop comparison useful. This is a requirements survey, not a product endorsement or a request for sensitive information.

**Audience:** adults who currently care for at least one pet in Singapore. **Estimated time:** 4–5 minutes. Participation is voluntary. Do not collect names, contact details, exact addresses, or medical records. Report only aggregated responses. Add the course/team's approved consent and data-retention wording before publishing.

## Intro / consent

We are a student team exploring a prototype marketplace for pet supplies. It lets users browse products from several fictional shops and compare prices. The prototype does not process real payments. Taking part is voluntary; answers will be used in aggregate for coursework. You may stop at any time. Do you agree to take part?

- Yes, continue (required to proceed)
- No (end survey)

## Questions

1. Which pet types do you currently care for? *(Select all: Dog, Cat, Rabbit, Bird, Fish, Other, Prefer not to say.)*
2. How often do you buy pet supplies? *(Weekly, Every 2–3 weeks, Monthly, Every 2–3 months, Less often.)*
3. Where do you usually buy them? *(Select all: Physical pet shop, Online marketplace, Retailer website, Veterinary clinic, Subscription/delivery service, Other.)*
4. Which product types do you buy most often? *(Select up to 3: Food, Treats, Health and hygiene, Toys, Accessories, Grooming supplies, Other.)*
5. When choosing a product, which factors matter most? *(Select up to 3: Price, Ingredients/materials, Brand familiarity, Reviews, Availability/stock, Delivery cost/speed, Shop trust, Product suitability for my pet.)*
6. How often do you compare the same product across shops before buying? *(Always, Often, Sometimes, Rarely, Never.)*
7. What makes comparing prices difficult today? *(Select all: Hard to find the same item, Too many websites, Prices/stock are unclear, Delivery costs differ, I do not compare, Other.)*
8. How useful would it be to see the same item and each shop's price and stock together? *(1 Not useful – 5 Very useful.)*
9. What information would you want on a product listing? *(Select up to 4: Price, Stock, Size/quantity, Ingredients/materials, Pet suitability, Shop name, Delivery details, Reviews, Image.)*
10. Would you use one basket for items from multiple shops if checkout clearly showed each shop's items and the total? *(Definitely, Probably, Not sure, Probably not, Definitely not.)*
11. What concerns would you have about buying from several shops in one checkout? *(Select all: Delivery timing/cost, Returns, Product authenticity, Payment/security, Split orders, None, Other.)*
12. What one change would make a product-comparison marketplace more useful to you? *(Optional free text; remind respondents not to include personal information.)*

## Simulated response summary

**Source:** [survey_responses_SIMULATED.csv](survey_responses_SIMULATED.csv), supplied for the course project. This is synthetic data, not a survey of real pet owners. Treat it only as a classroom requirements-analysis exercise; do not report these numbers as real-world user research.

**Sample:** 64 rows (R001?R064); all 64 have `consent=Yes`. Every respondent answered Q1?Q11; 50 answered the optional Q12. Multi-select counts below are respondent counts and may sum to more than 64. Percentages use 64 as the denominator unless noted.

- **Shopping frequency (Q2):** monthly 24/64 (37.5%); every 2?3 months 17 (26.6%); every 2?3 weeks 12 (18.8%); less often 7 (10.9%); weekly 4 (6.3%).
- **Where they shop (Q3, multi-select):** physical pet shops 43 (67.2%) and online marketplaces 43 (67.2%) were tied; veterinary clinics 23 (35.9%), retailer websites 17 (26.6%).
- **Common purchases (Q4, multi-select):** food 58 (90.6%), treats 30 (46.9%), toys 23 (35.9%), health and hygiene 18 (28.1%).
- **Purchase factors (Q5, multi-select):** price 36 (56.3%), ingredients/materials 30 (46.9%), suitability for the pet 28 (43.8%).
- **Current comparison habits (Q6):** always 12 (18.8%) or often 21 (32.8%); sometimes 17 (26.6%), rarely 11 (17.2%), never 3 (4.7%).
- **Comparison difficulties (Q7, multi-select):** finding the same item and unclear price/stock were tied at 38 each (59.4%); too many websites 37 (57.8%); differing delivery costs 27 (42.2%).
- **Usefulness of side-by-side price and stock (Q8):** mean 4.20/5, median 4; 51/64 (79.7%) rated it 4 or 5.
- **Listing information (Q9, multi-select):** price 29 (45.3%), stock 27 (42.2%), size/quantity and shop name 24 each (37.5%).
- **One basket across shops (Q10):** definitely 16 (25.0%) and probably 28 (43.8%), combined 44/64 (68.8%); 7 unsure (10.9%), 13 probably/definitely not (20.3%).
- **Concerns (Q11, multi-select):** delivery timing/cost 44 (68.8%), split orders 32 (50.0%), authenticity 26 (40.6%), returns 24 (37.5%), payment/security 20 (31.3%).
- **Optional comments (Q12):** 50 responses. Repeated themes include visible live stock, reliable matching of size/brand/flavour, delivery estimates and combined-delivery clarity, merchant/product legitimacy, reviews, vouchers, and quick reordering. These are qualitative themes from synthetic text, not evidence of demand.

## Implications for the course prototype

The synthetic answers support demonstrating the already scoped comparison basics: match equivalent products carefully, show each shop's price and stock together, and make merchant identity and pack size easy to scan. Clearly label checkout as simulated and show that one checkout creates shop-specific sub-orders. Delivery estimates, reviews, vouchers, saved items, unit-price comparison, and allergy filters are useful ideas to discuss as future work; the brief excludes or does not require several of them, so this dataset alone does not authorize expanding the MVP.

## D2 collection record

- Real-world collection: none. No actual pet owners were surveyed for this dataset.
- Dataset analyzed: the committed simulated CSV with 64 synthetic responses; analysis consists of descriptive counts and percentages, plus a manual grouping of optional comments.
- Reproducibility: each multi-select field was split on semicolons; blank Q12 values were excluded from comment themes. No respondent identities were present beyond synthetic row IDs.
- For the report, label all figures and comments as **simulated**. Do not describe them as recruited participants, user-testing findings, or representative Singapore market research.
