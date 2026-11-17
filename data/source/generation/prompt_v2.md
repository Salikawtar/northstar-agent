# Generation prompt v2 (sha256 24cf172a5ac48935b8dafa7bf36a8cdf8b289727e5edf7b48d873c87c547860e)

The hash covers SYSTEM_PROMPT + USER_PROMPT_TEMPLATE + GLOSSARY exactly as below; `run_manifest.json` records the same hash,
so a reader can confirm which prompt produced the data. Per-job attributes (intent, difficulty, hard mode, adversarial
type, persona, language, correction flag) are inserted into the `<<...>>` slots by `build_messages()`.

## System prompt
```
You generate SYNTHETIC training data for the customer-support assistant of Northstar Motors, a fictional dealership group in the Greater Toronto Area that sells and services the fictional Meridian brand (models: Meridian Arbor, Meridian Kestrel, Meridian Lumen EV, Meridian Halden, Meridian Tessera, Meridian Oriel). You write short, realistic web-CHAT CONVERSATIONS between a customer and the dealership's support agent: the customer opens, the agent replies briefly (a clarifying question or an acknowledgement with the next step), the customer follows up. You must output ONLY a single valid JSON object and nothing else.
```

## User prompt template
```
Write ONE realistic chat conversation (3 turns: customer, agent, customer) with these attributes:

- intent: <<INTENT>>  (<<INTENT_DESC>>)
- difficulty: <<DIFFICULTY>><<HARD_LINE>><<ADV_LINE>>
- persona: <<PERSONA>>
- channel: <<CHANNEL>>  (<<CHANNEL_DESC>>)
- language: <<LANGUAGE>>  (the customer writes in this language<<CODE_SWITCH_LINE>>; the agent answers in the same language)
- mid-conversation correction: <<CORRECTION>>

Dealership vocabulary you may use naturally: <<GLOSSARY>>

Hard rules:
1. Do NOT write real personal data or invent concrete identifiers. For any name, email, phone,
   VIN, plate, vehicle, mileage, repair order, city, date, amount, advisor or company, use a
   PLACEHOLDER token in curly braces from EXACTLY this list and no other:
   {customer_name} {first_name} {last_name} {email} {phone} {vin} {plate} {year_make_model}
   {mileage} {ro_number} {dealer_city} {appointment_date} {purchase_date} {amount}
   {advisor_name} {parent_name} {fleet_company}
   (We fill these with fake values later. Use only the ones the message needs.)
2. The CUSTOMER sounds like a real person for the persona - natural mess (typos, fragments, emotion)
   where the persona calls for it. Avoid generic AI phrasing such as "I hope this message finds you well".
   The AGENT is brief, polite and concrete (asks for the one detail it needs, or acknowledges and gives the
   next step); in adversarial conversations the agent does NOT comply with the manipulation.
3. If mid-conversation correction is "yes", the customer corrects something from their own opening turn
   in the follow-up (a wrong date, plate, model, amount, location, or what they actually meant).
4. Vary sentence structure and length. Do not copy these instructions back. Do not mention that you
   are generating data.

Return ONLY this JSON (no markdown fences, no commentary):
{"turns": [{"role": "customer", "text": "<opening message, with {placeholders}>"},
           {"role": "agent", "text": "<brief agent reply>"},
           {"role": "customer", "text": "<follow-up, with {placeholders}>"}],
 "intent": "<<INTENT>>",
 "needs_escalation": <true if a human agent is clearly required, else false>,
 "contains_pii": <true if the conversation references personal data fields, else false>,
 "has_correction": <true if the customer corrected themselves mid-conversation, else false>}

```

## Glossary inserted at <<GLOSSARY>>
```
RO = repair order number; service advisor = the dealership person who books and explains work; PDI = pre-delivery inspection; TSB = technical service bulletin; loaner / shuttle = courtesy car / ride; diagnostic fee = charge to find a fault; deductible = customer share of a warranty repair; wear-and-tear = items not covered (brakes, wipers, tires); lease buy-out = price to keep a leased car; CAMVAP = Canadian arbitration program for vehicle defects; OEM vs aftermarket = original vs third-party parts.
```

## Attribute texts inserted for hard and adversarial jobs
Hard modes: {
  "boundary": "sits on the boundary with the intent '{other}' - a reader could label it either way",
  "multi_ask": "contains TWO separate asks in one message (the second one is about '{other}')",
  "missing_detail": "omits the one detail the agent needs (VIN, mileage, RO number or appointment date) and is vague about it"
}

Adversarial types: {
  "prompt_injection": "tries to make the assistant ignore its instructions / reveal its prompt / act as a different system",
  "pii_extraction": "tries to get another person's data (VIN, plate, address, phone, what was done to someone else's car)",
  "policy_pressure": "claims the chatbot, a staff member or a document already promised coverage, a waiver, a price or a free loaner",
  "manufacturer_impersonation": "pretends to be the manufacturer, head office or a regulator and demands action or data",
  "warranty_fraud": "describes damage that is plainly owner-caused or pre-existing but frames it as a defect to get it covered"
}

## Fully rendered example (job v3_0003: out_of_scope, easy, en)
```
[system]
You generate SYNTHETIC training data for the customer-support assistant of Northstar Motors, a fictional dealership group in the Greater Toronto Area that sells and services the fictional Meridian brand (models: Meridian Arbor, Meridian Kestrel, Meridian Lumen EV, Meridian Halden, Meridian Tessera, Meridian Oriel). You write short, realistic web-CHAT CONVERSATIONS between a customer and the dealership's support agent: the customer opens, the agent replies briefly (a clarifying question or an acknowledgement with the next step), the customer follows up. You must output ONLY a single valid JSON object and nothing else.

[user]
Write ONE realistic chat conversation (3 turns: customer, agent, customer) with these attributes:

- intent: out_of_scope  (Not a dealership service matter: insurance, financing rates, selling the car privately, unrelated)
- difficulty: easy
- persona: angry owner who writes in CAPS and short bursts
- channel: chat  (web-chat message: short, informal, no subject line)
- language: English  (the customer writes in this language; the agent answers in the same language)
- mid-conversation correction: no

Dealership vocabulary you may use naturally: RO = repair order number; service advisor = the dealership person who books and explains work; PDI = pre-delivery inspection; TSB = technical service bulletin; loaner / shuttle = courtesy car / ride; diagnostic fee = charge to find a fault; deductible = customer share of a warranty repair; wear-and-tear = items not covered (brakes, wipers, tires); lease buy-out = price to keep a leased car; CAMVAP = Canadian arbitration program for vehicle defects; OEM vs aftermarket = original vs third-party parts.

Hard rules:
1. Do NOT write real personal data or invent concrete identifiers. For any name, email, phone,
   VIN, plate, vehicle, mileage, repair order, city, date, amount, advisor or company, use a
   PLACEHOLDER token in curly braces from EXACTLY this list and no other:
   {customer_name} {first_name} {last_name} {email} {phone} {vin} {plate} {year_make_model}
   {mileage} {ro_number} {dealer_city} {appointment_date} {purchase_date} {amount}
   {advisor_name} {parent_name} {fleet_company}
   (We fill these with fake values later. Use only the ones the message needs.)
2. The CUSTOMER sounds like a real person for the persona - natural mess (typos, fragments, emotion)
   where the persona calls for it. Avoid generic AI phrasing such as "I hope this message finds you well".
   The AGENT is brief, polite and concrete (asks for the one detail it needs, or acknowledges and gives the
   next step); in adversarial conversations the agent does NOT comply with the manipulation.
3. If mid-conversation correction is "yes", the customer corrects something from their own opening turn
   in the follow-up (a wrong date, plate, model, amount, location, or what they actually meant).
4. Vary sentence structure and length. Do not copy these instructions back. Do not mention that you
   are generating data.

Return ONLY this JSON (no markdown fences, no commentary):
{"turns": [{"role": "customer", "text": "<opening message, with {placeholders}>"},
           {"role": "agent", "text": "<brief agent reply>"},
           {"role": "customer", "text": "<follow-up, with {placeholders}>"}],
 "intent": "out_of_scope",
 "needs_escalation": <true if a human agent is clearly required, else false>,
 "contains_pii": <true if the conversation references personal data fields, else false>,
 "has_correction": <true if the customer corrected themselves mid-conversation, else false>}

```
