# Usability testing plan

**Purpose:** evaluate whether pet owners can complete the four MVP tasks using the end-to-end prototype. This is a plan and worksheet; no sessions or participant results are recorded here.

## Session setup

- Target: recruit 5–6 Singapore pet owners for sessions between 3 and 5 Nov 2026, per the project plan.
- Duration: about 25 minutes per participant, including briefing and debrief.
- Use the deployed dev site when the full vertical slices are ready; otherwise record the environment and treat a local session as formative only.
- Use fictional/sample pets, facilities and shops. The marketplace purchase is simulated and transfers no money.
- Ask permission before taking notes that could identify someone or recording a screen/voice. Participation is voluntary. Avoid collecting names, exact addresses, account credentials, or real pet medical information.
- The 64-row survey dataset is synthetic. Do not recruit or describe it as the usability sample.

## Moderator opening

“We are testing the prototype, not you. Please think aloud as you work. You can stop at any time. The shop and payment data are fictional; checkout is simulated and no real payment will occur. Please use only the sample information provided. Is it okay if I take anonymous notes?”

## Tasks

Give one task at a time. Do not point to controls unless the participant is blocked; note any help given.

1. **Pet record:** create a pet profile and add a vaccination record.
2. **Facility discovery:** find a nearby facility and filter the results to the facility type requested by the participant.
3. **Product discovery:** find a suitable item in the catalogue, compare its offers across shops, choose an in-stock offer, and add it to the basket.
4. **Simulated purchase:** review the basket and complete checkout, then explain what happened to the order and why the payment is simulated.

Use the same neutral wording for each participant. For task 2, let them choose a familiar Singapore postal district/area without recording their exact home address. For task 3, ask them to find a common pet-supply item rather than prescribing a merchant.

## Record for each task

| Participant code | Task | Start/end time | Completed without help? | Errors/backtracks | Help given | Confusion or notable quote |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

Do not fill in rows until sessions happen. Record task time in seconds; count an error when an action produces an unintended result or requires backtracking. Note moderator prompts separately from participant-initiated actions.

## Debrief prompts

- What was easiest or hardest?
- Were product identity, merchant, price and stock clear when comparing offers?
- Before completing checkout, was it clear that the purchase and payment were simulated?
- What would you change first?

## Analysis template

After sessions, report the number recruited and completing all tasks, completion rate and median time per task, errors/help by task, and recurring confusion points. Separate direct observations from interpretation. Remove identifying details from quotations. List resulting changes by severity and owner. Do not claim statistical representativeness for a 5–6 person formative sample.

## Recruitment status

No participants have been recruited and no sessions have been run. The planned window is 3–5 Nov 2026. Use the copy and tracker below to recruit and schedule 5–6 adults who currently care for a pet in Singapore. A team member must send the invitation and confirm the session format and location with each participant.

## Invitation template

**Subject:** Volunteer for a 25-minute pet-owner app usability session (3–5 Nov)

Hi! We are a student team testing a prototype for pet owners. We are looking for 5–6 adults in Singapore who currently care for a pet to try four short tasks in a 25-minute session between 3 and 5 November 2026. The tasks cover a pet record, finding a facility, comparing pet products, and a simulated checkout. Shops, products, pets and payment are sample data; no real payment will be made.

Taking part is voluntary. You can stop at any time. We will record anonymous task notes only; we will not ask for your name, exact address, account password or real pet medical information. We will not record audio or video unless you separately agree. If you are interested, please reply with a preferred time window and whether you prefer an in-person or remote session. We will confirm the details directly. Thank you!

Before sending, replace the contact instruction with the team's agreed reply channel. Do not promise compensation unless the team has approved it.

## Scheduling tracker

Use participant codes in this shared document. Keep names, contact details and exact locations out of it; the organizer can keep any necessary contact information separately and delete it after scheduling. Replace a slot with a confirmed time and environment only after agreement.

| Code | Status | Preferred window (SGT) | Format agreed | Session confirmed | Completed |
| --- | --- | --- | --- | --- | --- |
| U01 | Not contacted |  |  |  |  |
| U02 | Not contacted |  |  |  |  |
| U03 | Not contacted |  |  |  |  |
| U04 | Not contacted |  |  |  |  |
| U05 | Not contacted |  |  |  |  |
| U06 | Not contacted |  |  |  |  |

Record the actual test environment (deployed dev or local) on the observation sheet. If only local standalone mode is available, describe the session as formative and note that API-backed flows were not tested. Do not fill in participant or result rows before sessions happen. The 64-row survey dataset remains synthetic and is not part of this participant sample.
