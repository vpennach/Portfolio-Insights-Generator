# Project Context: Neuberger Berman Technical Assessment

## Background
I'm interviewing for an AI-focused role at Neuberger Berman. I have a Master's in Machine
Learning from Stevens Institute of Technology and an undergrad background in software
engineering. I completed an intro call with Amy (recruiter) that went well and moved
straight to next steps — this assessment is that next step.

AI assistance is explicitly permitted for this assessment (confirmed by Amy), but I need
to be able to explain the codebase line by line afterward. Understanding > speed. Please
build things collaboratively — explain what each piece of code does and why, rather than
just handing me a finished solution.

I haven't coded in a few months, so I may need refreshers on syntax/tooling as we go —
that's fine, just flag it and explain rather than assuming I remember.

## The Assessment
- Platform: HackerRank ("file upload" question type)
- Input: An Excel file (.xlsx) with some dataset
- Task: Build a dashboard — backend (Python, likely pandas for data processing) +
  frontend (React) — that analyzes/visualizes the data in the file
- Exact requirements (what fields, what charts, what endpoints) are unknown until the
  file/prompt is actually delivered — so we shouldn't over-build assumptions in advance
- Time constraints unknown — likely timed, so working efficiently once we see the real
  prompt matters

## Relevant Background / Portfolio (for context on my skill level)
- Statistical analysis project on Iron COR machine data
- Expected Goals (xG) soccer model built with a coach
- MLB pitch predictor
These show applied ML/data experience, though this assessment itself is more of a
data-engineering/full-stack task than an ML modeling task.

## Working Preferences
- Explain each step as we build — I need to walk through this code with the interviewer
- Prefer pandas for data processing on the backend
- Likely stack: Python backend (Flask or FastAPI — leaning toward whichever is faster to
  stand up cleanly) + React frontend
- Don't scaffold huge amounts of boilerplate I won't understand — keep it lean and
  explainable

## HackerRank-Specific Notes (from a practice round, may not apply to file-upload format)
- Don't modify locked stub code outside the function body if a stub is present
- Return types must match exactly what's expected
- "Run Code" vs "Submit" are different — Run Code checks visible samples only

## What I Need From You (Claude Code)
1. Once I upload/share the actual Excel file and prompt, help me understand the data
   first (structure, columns, types) before jumping to code
2. Propose a simple, clean architecture (backend endpoints + frontend components) and
   explain the reasoning
3. Build it step by step, explaining each file/function as we go
4. Help me prepare to explain the final result line by line
