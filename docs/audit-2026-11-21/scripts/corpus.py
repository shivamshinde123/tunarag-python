"""Shared real-world test corpus: a fictional company's support handbook (not in model priors)."""

DOCS = {
    "returns": "Brightwave Outfitters accepts returns within 45 days of delivery. Items must be unworn "
    "and keep their original tags. Final-sale items marked with a red dot cannot be returned.",
    "refunds": "Brightwave refunds go back to the original payment method within 7 business days after the "
    "warehouse in Tacoma inspects the return. Store credit is issued instantly instead if requested.",
    "shipping": "Standard shipping is free on orders over $85 and takes 4 to 6 business days. Express "
    "shipping costs $19 and arrives in 2 business days. Brightwave does not ship to PO boxes.",
    "warranty": "Every Brightwave tent and backpack carries a 3-year warranty against seam and zipper "
    "defects. Damage from campfires or pets is not covered by the warranty.",
    "loyalty": "The Trailhead loyalty program gives 3 points per dollar spent. 500 points can be redeemed "
    "for a $25 voucher. Points expire after 18 months without a purchase.",
    "repairs": "The Brightwave repair studio in Boise fixes jackets for a flat $30 fee. Repairs take "
    "about 3 weeks, and customers get a prepaid shipping label by email.",
    "sizing": "Brightwave jackets run one size small, so customers should order one size up. Boots run "
    "true to size, and wide-fit boots are marked with a W on the tag.",
    "support": "Customer support is open Monday to Saturday from 8am to 6pm Pacific time. The live chat "
    "agent is named Juniper, and phone support is at 1-800-555-0142.",
}

QUESTIONS = [
    {
        "id": "q-returns",
        "query": "How many days do I have to return an item to Brightwave?",
        "reference_answer": "45 days",
        "relevant_document_ids": ["returns"],
    },
    {
        "id": "q-refund",
        "query": "How long does a Brightwave refund take after inspection?",
        "reference_answer": "7 business days",
        "relevant_document_ids": ["refunds"],
    },
    {
        "id": "q-express",
        "query": "How much does express shipping cost?",
        "reference_answer": "$19",
        "relevant_document_ids": ["shipping"],
    },
    {
        "id": "q-warranty",
        "query": "How long is the warranty on Brightwave tents?",
        "reference_answer": "3 years",
        "relevant_document_ids": ["warranty"],
    },
    {
        "id": "q-points",
        "query": "How many loyalty points do I need for a $25 voucher?",
        "reference_answer": "500 points",
        "relevant_document_ids": ["loyalty"],
    },
    {
        "id": "q-repair",
        "query": "What does the Boise repair studio charge to fix a jacket?",
        "reference_answer": "$30",
        "relevant_document_ids": ["repairs"],
    },
    {
        "id": "q-chat",
        "query": "What is the name of the Brightwave live chat agent?",
        "reference_answer": "Juniper",
        "relevant_document_ids": ["support"],
    },
    {
        "id": "q-jacket-size",
        "query": "Should I order my normal size in a Brightwave jacket?",
        "reference_answer": "one size up",
        "relevant_document_ids": ["sizing"],
    },
]
