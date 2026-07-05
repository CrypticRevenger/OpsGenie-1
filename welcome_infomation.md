## Recommended flow

### Template (sent automatically)

Keep it very short:

```text
Hi {{1}} 👋

Welcome to OpsGenie.

Your account has been activated successfully.

I'm here to help you manage your business finances.

Reply with "Hi" or send any message to begin your setup.
```

This template gets you inside WhatsApp's conversation window.

---

## Then the AI takes over

As soon as the distributor replies with anything ("Hi", "Hello", 👍, etc.), the onboarding state machine starts.

For example:

**OpsGenie**

> Welcome! I'll help you set up your business in about 5–10 minutes.
>
> First, what kind of business do you run?
>
> Examples:
> • FMCG Distributor
> • Pharma Distributor
> • Chicken Feed Distributor

User:

> FMCG Distributor

Save:

```json
{
  "business_type": "FMCG Distributor"
}
```

---

Then:

> Great! Now let's add the products you sell.
>
> Send them one by one.
>
> Type **Done** when you're finished.

User:

```
Rice
```

Save.

User:

```
Oil
```

Save.

User:

```
Sugar
```

Save.

User:

```
Done
```

Move to suppliers.

---

## Everything should be conversational

Don't ask for three fields at once like:

```
Supplier Name
Phone
Payment Days
```

Instead:

```
What's your first supplier's name?
```

↓

```
ABC Foods
```

↓

```
What's their phone number?
```

↓

```
9876543210
```

↓

```
How many credit days do they usually give you?
```

↓

```
15
```

↓

```
Would you like to add another supplier?
```

**Yes / No**

This feels much more natural.

---

## The same pattern works for dealers

Ask:

```
Dealer name?
```

↓

```
Phone number?
```

↓

```
Credit days?
```

↓

```
Add another dealer?
```

---

## Financial data

```
How much money is currently available in your bank account?
```

↓

```
₹3,20,000
```

Save as:

```json
{
    "opening_bank_balance": 320000
}
```

---

## Receivables

```
Does any dealer currently owe you money?

Yes / No
```

If **Yes**:

```
Dealer name?
```

↓

```
Amount?
```

↓

```
Expected payment date?
```

↓

```
Add another outstanding?
```

---

## Supplier dues

Exactly the same pattern.

---

## Inventory

```
Would you like to enter your current stock?

Yes / No
```

If **No**, simply record:

```json
{
    "inventory_initialized": false
}
```

and continue.

---

## Business habits

These are extremely valuable because they let OpsGenie personalize its behavior.

Ask things like:

* When do you usually send invoices?
* When do you usually collect payments?
* What time would you like your morning briefing?
* Which language do you prefer for messages?
* What day does your accounting week start?
* Which bank do you primarily use? (optional)

---

## Final message

```
🎉 Setup complete!

You're all set.

Starting tomorrow morning, I'll send your business briefing.

You can now ask me things like:

• Create Invoice
• Record Payment
• Outstanding Report
• Supplier Due
• Cash Position
• Inventory Status

I'm always available on WhatsApp whenever you need me.
```

---

## One architectural suggestion

Since we've previously discussed your backend phases and agent design, I would **not hardcode these 10 steps** into the AI prompt.

Instead, create an **Onboarding Engine** with:

* A database table to track the user's current onboarding step.
* A state machine (e.g., `BUSINESS_TYPE`, `PRODUCTS`, `SUPPLIERS`, `DEALERS`, etc.).
* Validation for each step (phone number, date, amount, yes/no).
* The AI responsible only for understanding the user's message and extracting data, while the state machine decides what to ask next.

This approach is far more reliable than relying on the LLM alone to remember where the user is in the onboarding process, and it will make your onboarding much easier to maintain and extend.
