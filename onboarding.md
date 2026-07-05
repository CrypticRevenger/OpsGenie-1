**what information should be collected on the website and what information should be collected by the WhatsApp AI Agent during onboarding for a brand-new distributor.**

I actually think this is one of the most important UX decisions in the whole product.

The principle I'd follow is:

> **Website collects information that is easier with forms.**
>
> **WhatsApp collects information that is conversational and business-related.**

---

# Phase 1 — Website (5 minutes)

The goal is only to create the company and activate the service.

## Account Details

* Company Name
* Owner Name
* Mobile Number (WhatsApp Number)
* Email
* Password / OTP Login

---

## Business Details

* Business Type
* Language
* City
* GST (Optional)

---

## Subscription

* Select Plan
* Payment
* Activate Account

---

## That's it.

Then immediately show:

> **"Your WhatsApp Business Assistant is ready. Open WhatsApp to complete your business setup."**

No dealers.

No inventory.

No products.

No invoices.

---

# Phase 2 — WhatsApp AI Setup

Now the real onboarding starts.

---

### Message 1

```
👋 Hi Spandan!

Welcome to OpsGenie.

I'll help you manage your business through WhatsApp.

Let's setup your business.

This will take around 10–15 minutes.

Ready?
```

---

## Step 1 — Business Understanding

Instead of asking for everything.

Ask

```
What kind of business do you run?

Example:

FMCG Distributor

Pharma Distributor

Chicken Feed Distributor
```

This helps the AI understand context.

---

## Step 2 — Products

```
Let's add your products.

Send them one by one.

Example:

Rice

Dal

Oil
```

or

```
Rice

Dal

Sugar

Oil
```

AI saves all.

---

## Step 3 — Suppliers

```
Now tell me about your suppliers.

Example:

ABC Foods

9876543210

Payment in 15 days
```

Repeat until done.

---

## Step 4 — Dealers

```
Now let's add your dealers.

Dealer Name

Phone

Credit Days
```

Again conversational.

---

## Step 5 — Opening Financial Position

```
How much money is currently in your bank account?
```

↓

```
₹3,20,000
```

---

## Step 6 — Pending Receivables

```
Do any dealers currently owe you money?

Yes / No
```

If Yes

```
Dealer Name

Amount

Expected Payment Date
```

Repeat.

---

## Step 7 — Pending Supplier Payments

```
Do you have any supplier payments pending?

Yes / No
```

If Yes

```
Supplier

Amount

Due Date
```

---

## Step 8 — Opening Inventory

```
Would you like to enter your current stock?

Yes

No
```

If Yes

```
Rice

500kg
```

Repeat.

If No

```
No problem.

We'll start tracking inventory from your next invoice.
```

This is much better UX.

---

## Step 9 — Business Habits

These are questions no form should ask.

```
When do you usually send invoices?

Immediately

Evening

End of Day
```

---

```
When do you usually collect payments?
```

---

```
What time should I send your morning briefing?

7 AM

8 AM

9 AM
```

---

## Step 10 — Finish

```
🎉 Setup Complete!

Starting tomorrow morning,

I'll send you your first business briefing.

You can also ask me things like:

• Create Invoice
• Ram Outstanding
• Cash Position
• Supplier Due
• Inventory Status
```

---

# Why I like this split

### Website

Collects **Identity**.

```text
Who are you?
```

---

### WhatsApp

Collects **Business**.

```text
How does your business work?
```

---

# One thing I would add (this is important)

Don't force them to finish everything in one sitting.

For example:

```
Current Setup Progress

Company ✅

Products ✅

Suppliers ❌

Dealers ❌

Inventory ❌

Pending Payments ❌

Completion

42%
```

Every time they open WhatsApp:

```
Let's continue your setup.

Next step:

Add your dealers.
```

This is much friendlier than forcing a 30-minute onboarding session.

---

# One thing I would change from our earlier discussions

After thinking through your product philosophy, **I would not ask them to manually enter 50 dealers one by one if they already have a structured list**.

Instead, during WhatsApp onboarding, give them the choice:

```
How would you like to add your dealers?

1. Send one by one in chat.

2. Upload an Excel/CSV file.

3. Import from Tally (Future).

4. I'll add them later.
```

Even if you don't implement options 2 and 3 immediately, designing for them now makes the onboarding scalable. A distributor with 100 dealers shouldn't have to type each one manually into WhatsApp.
