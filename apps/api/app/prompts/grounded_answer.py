GROUNDED_ANSWER_PROMPT = """\
You are a retrieval-grounded assistant.
Answer ONLY from the provided context below.
If the answer is not fully supported by the context, say so clearly.
Always cite the source document and page number when referring to specific information.
Do not invent file names, page numbers, or facts.
Distinguish fact from inference.

Context:
{context}

Question: {query}

Answer:
"""

PAGE_SUMMARY_PROMPT = """\
Summarize this page for retrieval.
Focus on topics, entities, obligations, deadlines, policy names, and visible chart or figure mentions.
Keep it short and searchable.

Page content:
{content}

Summary:
"""

IMAGE_CAPTION_PROMPT = """\
Generate a concise retrieval-oriented description of this image.
Mention visible objects, readable text, layout style, colors, and document-like properties.
Do not speculate beyond what is clearly visible.

Caption:
"""

QUERY_CLASSIFY_PROMPT = """\
Classify the following search query into exactly one category.

Categories:
- text: looking for written content, facts, policies, or document text
- image: looking for visual content, photos, charts, diagrams, or figures
- hybrid: query may match both text and images
- summary: asking for an overview or summary of one or more documents
- compare: asking to compare two or more documents or items

Query: {query}

Category (one word only):
"""
