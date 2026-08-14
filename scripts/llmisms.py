#!/usr/bin/env python3
"""llmisms.py -- strip the tics out of LLM prose.

A rule database plus a rewriter. Runs standalone or as a library.

    python3 llmisms.py notes.md              rewrite to stdout
    python3 llmisms.py --check notes.md      report hits, change nothing
    python3 llmisms.py --in-place notes.md   rewrite the file
    python3 llmisms.py --list                dump the rule database
    python3 llmisms.py --selftest            run the built-in tests
    cat x.md | python3 llmisms.py            read stdin

    from llmisms import scrub
    text, counts = scrub(text)

Rules live in RULES, grouped by category. Categories in DEFAULT_ON run unless
you say otherwise; the rest are opt-in with --on. Flag-only rules never
rewrite anything -- they only show up under --check, because the fix needs a
human.

Code is protected. Fenced blocks, inline backticks, indented blocks, HTML
tags, URLs, and markdown link targets are masked before any rule runs, so a
variable named `leverage` survives untouched.
"""

import argparse
import hashlib
import re
import sys

# --- replacement markers ---------------------------------------------------

X = ""        # delete outright, for mid-sentence words
CUT = "\x01"  # delete and capitalize whatever follows, for sentence openers
FLAG = None   # report only, never rewrite

CAPFIX = "\x01"

# A replacement can also be:
#   a tuple of strings  -- rotate between them, so one word does not collapse
#                          onto one replacement everywhere (see `pick`)
#   a function          -- for rules that need to see what surrounds the match
CALLABLE_LABELS = {}


def _roll(m, salt=""):
    """A stable number in [0, 1) derived from the match and its context.

    Uniform output is itself a tell: swapping every "utilize" and every
    "leverage" onto "use" leaves prose that repeats one word unnaturally, and
    deleting every single "very" reads as surgically terse. So some rules vary
    what they do. Varying it randomly would make the hooks nondeterministic
    and untestable, so the choice is keyed off the surrounding text: the same
    input always gives the same output, but two occurrences in different
    sentences usually differ.

    Python's hash() is salted per process, so it cannot be used here.
    """
    seed = m.string[max(0, m.start() - 40):m.start()] + m.group(0) + salt
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(1 << 64)


def pick(options, m):
    """Choose one of several replacements, stably, from context."""
    return options[int(_roll(m) * len(options)) % len(options)]


def sometimes(rate, label):
    """Delete the match `rate` of the time, keep it otherwise."""
    def repl(m):
        return "" if _roll(m, "drop") < rate else m.group(0)
    CALLABLE_LABELS[repl] = label
    return repl


def contract(short):
    """Contract, unless the writer shouted it -- "DO NOT" is emphasis."""
    def repl(m):
        if m.group(0).isupper():
            return m.group(0)
        return _match_case(m.group(0), short)
    CALLABLE_LABELS[repl] = "-> " + short.strip()
    return repl


def em_dash(m):
    """Turn an em-dash into a comma, unless the context says leave it.

    Preserved: line-initial dashes (attributions, list markers) and numeric
    ranges. Dropped entirely when it dangles at the end of a line, or reduced
    to a space when the preceding character already carries the pause.
    """
    text = m.string
    before = text[m.start() - 1] if m.start() else ""
    after = text[m.end()] if m.end() < len(text) else ""

    if before in ("", "\n"):
        return m.group(0)               # "-- Anonymous", or a list marker
    if before.isdigit() and after.isdigit():
        return m.group(0)               # 1914-1918
    if after in ("", "\n"):
        return ""                       # dangling at end of line
    if before in ",;:.!?":
        return " "                      # the pause is already there
    return ", "


CALLABLE_LABELS[em_dash] = "-> , (context aware)"

# Past participles, for telling auxiliary "have" from main-verb "have".
PARTICIPLE = (r"(?:been|had|got|gotten|done|seen|made|found|taken|given|written|read|set|put|"
              r"come|become|run|built|kept|left|sent|told|thought|brought|bought|caught|taught|"
              r"held|meant|met|paid|said|shown|known|grown|drawn|chosen|broken|spoken|driven|"
              r"risen|fallen|eaten|begun|gone|lost|won|felt|heard|let|hit|cut|shut|spent|stood|"
              r"understood|\w+ed)")


class Rule:
    __slots__ = ("cat", "pat", "repl", "note")

    def __init__(self, cat, pattern, repl, note):
        self.cat = cat
        self.pat = re.compile(pattern, re.IGNORECASE)
        self.repl = repl
        self.note = note


def R(cat, pattern, repl, note):
    return Rule(cat, pattern, repl, note)


def V(cat, src, dst):
    """Expand a verb swap across its forms, keeping agreement intact.

    Both arguments are (base, third-person, past, gerund) tuples; use None to
    skip a form. Swapping a bare stem is not enough -- "demonstrates" mapped
    onto "show" gives "This show the bug", so every form needs its own pair.
    """
    return [R(cat, r"\b%s\b" % s, d, s) for s, d in zip(src, dst) if s and d]


# --- the database ----------------------------------------------------------
#
# Order matters. Long phrases come before the words they contain, so
# "delve into" wins before "delve" ever sees the text.

RULES = [
    # -- sycophancy: praise and eagerness nobody asked for ------------------
    R("sycophancy", r"\b(?:that(?:'s| is)|what)\s+(?:a\s+)?(?:really\s+|very\s+)?"
      r"(?:great|good|excellent|fantastic|interesting|fascinating|insightful|thoughtful|smart|sharp)\s+"
      r"(?:question|point|observation|catch|idea|call)[.!]*\s*", CUT, "That's a great question!"),
    R("sycophancy", r"\b(?:great|good|excellent|nice|perfect|fantastic|brilliant)\s+"
      r"(?:question|point|catch|observation|idea|call|thinking)[.!]+\s*", CUT, "Great catch!"),
    R("sycophancy", r"\byou(?:'re| are)\s+(?:absolutely\s+|completely\s+|totally\s+|100%\s+)?right[.!,]*\s*",
      CUT, "You're absolutely right"),
    R("sycophancy", r"\byou(?:'ve| have) (?:hit the nail on the head|nailed it)[.!]*\s*", CUT, "you nailed it"),
    R("sycophancy", r"\bi(?:'d| would) be (?:happy|glad|delighted|more than happy) to\s+"
      r"(?:help(?:\s+(?:you\s+)?with (?:that|this))?|assist(?:\s+you)?)[.!]*\s*", CUT, "I'd be happy to help"),
    R("sycophancy", r"\b(?:absolutely|certainly|sure thing|of course|definitely|indeed)[!,.]+\s*",
      CUT, "Certainly!"),
    R("sycophancy", r"\bthanks?(?: you)? for (?:asking|the question|sharing|bringing (?:that|this) up)[.!]*\s*",
      CUT, "Thanks for asking!"),
    R("sycophancy", r"\bgreat (?:work|job|progress)[!.]+\s*", CUT, "Great work!"),
    R("sycophancy", r"\bi apologize for (?:the|any) (?:confusion|oversight|mistake|error)[.!]*\s*",
      CUT, "I apologize for the confusion"),
    R("sycophancy", r"\byou raise an? (?:great|good|excellent|important|valid) point[.!]*\s*",
      CUT, "You raise a good point"),
    R("sycophancy", r"\b(?:as an ai(?: language model)?|i(?:'m| am) an ai)[,]?\s*", CUT, "As an AI language model"),

    # -- filler: throat-clearing before the actual sentence -----------------
    R("filler", r"\bit(?:'s| is) (?:important|worth|crucial|essential|vital|helpful|useful|good) to\s+"
      r"(?:note|mention|remember|point out|highlight|understand|keep in mind|be aware)\s+that\s+",
      CUT, "It's important to note that"),
    R("filler", r"\bit(?:'s| is) worth (?:noting|mentioning|remembering|pointing out|highlighting)\s+that\s+",
      CUT, "It's worth noting that"),
    R("filler", r"\bit should be (?:noted|mentioned|pointed out|emphasized)\s+that\s+", CUT, "It should be noted that"),
    R("filler", r"\bplease (?:note|be aware|keep in mind|remember)\s+that\s+", CUT, "Please note that"),
    R("filler", r"\b(?:keep|bear) in mind that\s+", CUT, "Keep in mind that"),
    R("filler", r"\bas (?:you (?:may|might) (?:know|be aware|recall)|we(?:'ve| have) (?:seen|discussed)|"
      r"mentioned (?:earlier|above|previously)|previously mentioned|noted above|discussed earlier)[,]?\s+",
      CUT, "As mentioned earlier"),
    R("filler", r"\b(?:that being said|with that said|having said that|that said)[,]?\s+", "Still, ", "That being said"),
    R("filler", r"\bneedless to say[,]?\s+", CUT, "Needless to say"),
    R("filler", r"\bi think it(?:'s| is) (?:fair|safe) to say that\s+", CUT, "It's fair to say that"),
    R("filler", r"\bat the end of the day[,]?\s+", CUT, "At the end of the day"),
    R("filler", r"\bwhen (?:it comes down to it|all is said and done)[,]?\s+", CUT, "When it comes down to it"),
    R("filler", r"\badditionally[,]\s+", "Also, ", "Additionally,"),
    R("filler", r"\bfurthermore[,]\s+", "Also, ", "Furthermore,"),
    R("filler", r"\bmoreover[,]\s+", "Also, ", "Moreover,"),
    R("filler", r"\bfirst and foremost[,]?\s+", "First, ", "First and foremost"),
    R("filler", r"\blast but not least[,]?\s+", "Finally, ", "Last but not least"),
    R("filler", r"\bin (?:my|our) (?:humble )?opinion[,]?\s+", CUT, "In my humble opinion"),
    R("filler", r"\bthe (?:fact|reality|truth) (?:of the matter )?is(?: that)?[,]?\s+", CUT, "The truth is"),
    R("filler", r"\bhere(?:'s| is) the thing[:,.]?\s+", CUT, "Here's the thing"),
    R("filler", r"\bmake no mistake[,]?\s+", CUT, "Make no mistake"),
    R("filler", r"\blet that sink in[.!]*\s*", X, "Let that sink in"),
    R("filler", r"\b(?:spoiler alert|buckle up|plot twist)[:,.!]?\s+", CUT, "Buckle up"),
    R("filler", r"\bwithout further ado[,]?\s+", CUT, "Without further ado"),
    R("filler", r"\blet(?:'s| us) (?:dive|jump|dig) (?:right )?(?:in|into it)[.!]*\s*", X, "Let's dive in"),

    # -- wordy connectives: long link, short link ---------------------------
    R("filler", r"\bin order to\b", "to", "in order to"),
    R("filler", r"\bin order for\b", "for", "in order for"),
    R("filler", r"\bdue to the fact that\b", "because", "due to the fact that"),
    R("filler", r"\bowing to the fact that\b", "because", "owing to the fact that"),
    R("filler", r"\b(?:in spite of|despite) the fact that\b", "although", "despite the fact that"),
    R("filler", r"\bfor the purposes? of\b", "for", "for the purpose of"),
    R("filler", r"\bin the event that\b", "if", "in the event that"),
    R("filler", r"\bat (?:this|the present) (?:point|moment) in time\b", "now", "at this point in time"),
    R("filler", r"\bwhen it comes to\b", "for", "when it comes to"),
    R("filler", r"\bin terms of\b", "for", "in terms of"),
    R("filler", r"\bwith regards? to\b", "about", "with regard to"),
    R("filler", r"\bin (?:relation|reference) to\b", "about", "in relation to"),
    R("filler", r"\bpertaining to\b", "about", "pertaining to"),
    R("filler", r"\bprior to\b", "before", "prior to"),
    R("filler", r"\bsubsequent to\b", "after", "subsequent to"),
    R("filler", r"\bin the near future\b", "soon", "in the near future"),
    R("filler", r"\ba (?:large |great |significant )?number of\b", "many", "a number of"),
    R("filler", r"\bthe (?:vast |overwhelming )?majority of\b", "most", "the majority of"),
    R("filler", r"\b(?:is|are) able to\b", "can", "is able to"),
    R("filler", r"\bhas the ability to\b", "can", "has the ability to"),
    R("filler", r"\bmake use of\b", "use", "make use of"),
    R("filler", r"\beach and every\b", "every", "each and every"),
    R("filler", r"\bwhether or not\b", "whether", "whether or not"),
    R("filler", r"\bit (?:is|'s) (?:recommended|advisable) that you\b", "you should", "it is recommended that you"),
    R("filler", r"\bplays? an? (?:important|crucial|key|vital|significant|critical|central) role in\b",
      "matters for", "plays a crucial role in"),

    # -- closers: sign-offs at the end of every single reply ----------------
    R("closer", r"\b(?:i )?hope (?:this|that) helps[.!]*\s*", X, "I hope this helps!"),
    R("closer", r"\b(?:please )?(?:let me know|feel free to (?:ask|reach out|let me know))\s*"
      r"(?:if|should|when)[^.!?\n]*[.!?]\s*", X, "Let me know if you have questions"),
    R("closer", r"\blet me know if you(?:'d| would) like[^.!?\n]*[.!?]\s*", X, "Let me know if you'd like"),
    R("closer", r"\bfeel free to[^.!?\n]*[.!?]\s*", X, "Feel free to..."),
    R("closer", r"\b(?:please )?don't hesitate to[^.!?\n]*[.!?]\s*", X, "Don't hesitate to..."),
    R("closer", r"\bhappy (?:coding|hacking|building|debugging)[!.]*\s*", X, "Happy coding!"),
    R("closer", r"\bin conclusion[,]?\s+", CUT, "In conclusion"),
    R("closer", r"\bto (?:summarize|sum up|wrap up|recap)[,]?\s+", CUT, "To summarize"),
    R("closer", r"\b(?:overall|all in all|in summary|in short)[,]\s+", CUT, "Overall,"),
    R("closer", r"\bthe key takeaway (?:here )?is that\s+", CUT, "The key takeaway is"),
    R("closer", r"\bremember[,]\s+", CUT, "Remember,"),

    # -- cliche: metaphors worn smooth --------------------------------------
    R("cliche", r"\bin today(?:'s)? (?:fast[- ]paced |modern |digital )?(?:world|age|landscape|era)[,]?\s*",
      CUT, "in today's fast-paced world"),
    R("cliche", r"\bin the ever[- ](?:evolving|changing|shifting) (?:world|landscape|field|realm) of\b",
      "in", "in the ever-evolving landscape of"),
    R("cliche", r"\bin the (?:realm|world|landscape|sphere|domain|arena) of\b", "in", "in the realm of"),
    # bare form, minus "domain" and "landscape" -- both have honest technical uses
    R("cliche", r"\bthe (?:realm|sphere|arena|world) of\b", X, "the realm of"),
    R("cliche", r"\bnavigating the (?:complexities|challenges|intricacies|landscape|nuances) of\b",
      "handling", "navigating the complexities of"),
    R("cliche", r"\b(?:stands?|serves?) as a testament to\b", "shows", "stands as a testament to"),
    R("cliche", r"\ba testament to\b", "proof of", "a testament to"),
    R("cliche", r"\ba (?:rich |vibrant |complex )?tapestry of\b", "mix of", "a rich tapestry of"),
    R("cliche", r"\ba treasure trove of\b", "lots of", "a treasure trove of"),
    R("cliche", r"\ba beacon of\b", "a model of", "a beacon of"),
    R("cliche", r"\bat the forefront of\b", "leading", "at the forefront of"),
    R("cliche", r"\bthe backbone of\b", "the core of", "the backbone of"),
    R("cliche", r"\bat the heart of\b", "central to", "at the heart of"),
    R("cliche", r"\b(?:unlock|unleash|harness) the (?:power|potential|full potential) of\b", "use",
      "unlock the power of"),
    R("cliche", r"\bempowers? (?:you|users|teams|developers) to\b", "lets you", "empowers you to"),
    R("cliche", r"\btake (?:it|things|your \w+) to the next level\b", "improve it", "take it to the next level"),
    R("cliche", r"\bthe sky(?:'s| is) the limit[.!]*\s*", X, "the sky's the limit"),
    R("cliche", r"\bthink outside the box\b", "try something new", "think outside the box"),
    R("cliche", r"\blow[- ]hanging fruit\b", "easy wins", "low-hanging fruit"),
    R("cliche", r"\bparadigm shift\b", "big change", "paradigm shift"),
    R("cliche", r"\ba game[- ]chang(?:er|ing)\b", "a big deal", "game-changer"),
    R("cliche", r"\bmov(?:e|es|ing) the needle\b", "make a difference", "move the needle"),
    R("cliche", r"\bboil the ocean\b", "do everything at once", "boil the ocean"),
    R("cliche", r"\bdouble[- ]edged sword\b", "trade-off", "double-edged sword"),
    R("cliche", r"\b(?:the )?tip of the iceberg\b", "only the start", "tip of the iceberg"),
    R("cliche", r"\b(?:deep[- ]div(?:e|ing)|dive deep) into\b", "study", "deep dive into"),
    R("cliche", r"\bdelv(?:e|es|ing) into\b", "dig into", "delve into"),
    R("cliche", r"\bdelved into\b", "dug into", "delved into"),
    R("cliche", r"\bdelv(?:e|es|ing)\b", "dig", "delve"),

    # -- puffery: inflating how much the subject matters --------------------
    # Wikipedia's WP:AILEGACY list. LLMs pad a topic with claims about its
    # significance, legacy, and place in some broader trend.
    R("puffery", r"\bmarking an? (?:pivotal|significant|key|major|important|defining)\s+"
      r"(?:moment|milestone|turning point|shift|chapter)\b", X, "marking a pivotal moment"),
    R("puffery", r"\brepresent(?:s|ed) an? (?:significant|major|profound|pivotal|key)\s+"
      r"(?:shift|change|milestone|departure|leap)\b", "is a shift", "represents a significant shift"),
    R("puffery", r"\bunderscor(?:es|ing|ed) (?:its|the|their|his|her) "
      r"(?:importance|significance|role|value|impact)\b", "matters", "underscores its importance"),
    R("puffery", r"\bhighlight(?:s|ing|ed) (?:its|the|their) (?:importance|significance)\b",
      "matters", "highlights its significance"),
    R("puffery", r"\breflect(?:s|ing|ed) (?:a |the )?broader\b", "reflects", "reflects broader"),
    R("puffery", r"\bsetting the stage for\b", "leading to", "setting the stage for"),
    R("puffery", r"\bcontributing to the broader\b", "adding to the", "contributing to the broader"),
    R("puffery", r"\bleav(?:es|ing|e) an indelible mark(?: on)?\b", "lasts", "indelible mark"),
    R("puffery", r"\bdeeply rooted in\b", "rooted in", "deeply rooted in"),
    R("puffery", r"\ba focal point (?:of|for|in)\b", "a center of", "focal point"),
    R("puffery", r"\bplays? an? role in\b", "affects", "plays a role in"),
    R("puffery", r"\bcement(?:s|ing|ed) (?:its|his|her|their) "
      r"(?:place|role|status|position|legacy|reputation)\b", X, "cementing its place"),
    R("puffery", r"\ba (?:rich|vibrant|diverse|storied|proud) (?:cultural |local )?"
      r"(?:heritage|history|tradition)\b", "a history", "rich cultural heritage"),
    R("puffery", r"\ba diverse (?:array|range|selection) of\b", "a range of", "a diverse array of"),
    R("puffery", r"\bnestled (?:in|within|among|amid|between)\b", "in", "nestled in"),
    R("puffery", r"\bin the heart of\b", "in", "in the heart of"),
    R("puffery", r"\b(?:stunning|breathtaking) natural beauty\b", "scenery", "stunning natural beauty"),
    R("puffery", r"\bmaintains? an? (?:active|strong|robust) "
      r"(?:social media |digital |online )?presence\b", "is active online", "active social media presence"),
    R("puffery", r"\brenowned for\b", "known for", "renowned for"),
    R("puffery", r"\bwidely (?:regarded|recognized|recognised|considered|hailed) as\b",
      "seen as", "widely regarded as"),
    R("puffery", r"\ban? (?:key|pivotal|crucial|major) turning point\b", "a turning point",
      "key turning point"),
    R("puffery", r"\bfaces? (?:several |a number of |numerous |many )?challenges\b",
      "has problems", "faces challenges"),
    R("puffery", r"\bstands? as an? (?:vibrant|shining|lasting|enduring|powerful)\b", "is a",
      "stands as a vibrant"),

    # -- copula: LLMs avoid plain "is" and "has" ----------------------------
    # Wikipedia documents a measurable drop in is/are after 2022, with
    # marketing verbs standing in for them.
    R("copula", r"\bboasts an?\b", "has a", "boasts a"),
    R("copula", r"\bboasts\b", "has", "boasts"),
    R("copula", r"\b(?:serves|stands|functions|operates|acts) as an?\b", "is a", "serves as a"),
    R("copula", r"\b(?:serves|stands|functions|operates|acts) as\b", "is", "serves as"),
    R("copula", r"\bis home to\b", "has", "is home to"),
    R("copula", r"\brepresents an?\b", "is a", "represents a"),
    R("copula", r"\bventured into\b", "entered", "ventured into"),

    # -- chatbot: assistant-speak that leaked into the text -----------------
    R("chatbot", r"\bas of my last (?:knowledge |training )?(?:update|cutoff)"
      r"[^.,!?\n]{0,40}[.,]\s*", CUT, "as of my last knowledge update"),
    R("chatbot", r"\bi (?:don't|do not) have (?:specific |any |detailed )?"
      r"(?:information|data|details|access)\b[^.!?\n]{0,80}[.!?]\s*", X, "I don't have information about"),
    R("chatbot", r"\bbased on (?:the )?(?:available|provided) "
      r"(?:information|sources|data|results)[,]?\s*", CUT, "based on available information"),
    # split by number so the replacement stays grammatical
    R("chatbot", r"\bare(?: not|n't) (?:widely|extensively|fully|publicly|readily) "
      r"(?:documented|available|transcribed|disclosed|known|recorded)\b", "are unclear",
      "are not widely documented"),
    R("chatbot", r"\bwere(?: not|n't) (?:widely|extensively|fully|publicly|readily) "
      r"(?:documented|available|transcribed|disclosed|known|recorded)\b", "were unclear",
      "were not widely documented"),
    R("chatbot", r"\bwas(?: not|n't) (?:widely|extensively|fully|publicly|readily) "
      r"(?:documented|available|transcribed|disclosed|known|recorded)\b", "was unclear",
      "was not widely documented"),
    R("chatbot", r"\bis(?: not|n't) (?:widely|extensively|fully|publicly|readily) "
      r"(?:documented|available|transcribed|disclosed|known|recorded)\b", "is unclear",
      "is not widely documented"),
    R("chatbot", r"\bin the (?:provided|available) (?:search results|sources|context|documents)\b",
      "in the sources", "in the provided search results"),
    R("chatbot", r"\bwould you like me to\b[^.!?\n]{0,100}[.?!]\s*", X, "Would you like me to..."),
    R("chatbot", r"\bshall i\b[^.!?\n]{0,80}\?\s*", X, "Shall I...?"),
    R("chatbot", r"\bmy analysis is based on\b[^.!?\n]{0,100}[.!?]\s*", X, "My analysis is based on"),
    R("chatbot", r"\bmaintains? a low profile\b", "is private", "maintains a low profile"),
    # placeholders: never rewrite these, you want to see them
    R("chatbot", r"\[(?:your name|your \w+|entertainer's name|insert[^\]\n]{0,40}|"
      r"link to [^\]\n]{0,40}|add [^\]\n]{0,40})\]", FLAG, "placeholder text"),
    R("chatbot", r"\b(?:INSERT|PASTE|SOURCE|REPLACE)_[A-Z0-9_]{3,}\b", FLAG, "placeholder token"),

    # -- corporate: meeting-room verbs --------------------------------------
    R("corporate", r"\bcircle back\b", "come back", "circle back"),
    R("corporate", r"\btouch base\b", "talk", "touch base"),
    R("corporate", r"\breach out to\b", "ask", "reach out to"),
    R("corporate", r"\breach out\b", "get in touch", "reach out"),
    R("corporate", r"\blevel up\b", "improve", "level up"),
    R("corporate", r"\bdouble[- ]click on\b", "look closer at", "double-click on"),
    R("corporate", r"\bunpack(?:s|ing)? (?:this|that|it)\b", "explain it", "unpack this"),
    R("corporate", r"\bsynerg(?:y|ies|istic)\b", "fit", "synergy"),
    R("corporate", r"\bholistic(?:ally)?\b", "whole", "holistic"),
    R("corporate", r"\bactionable insights?\b", "next steps", "actionable insights"),
    R("corporate", r"\bbest[- ]in[- ]class\b", X, "best-in-class"),
    R("corporate", r"\bmission[- ]critical\b", "critical", "mission-critical"),

    # -- hype: marketing adjectives and dead intensifiers -------------------
    R("hype", r"\b(?:very|really|truly|extremely|incredibly|highly|quite|remarkably|"
      r"exceptionally|tremendously|immensely)\s+", sometimes(0.75, "(delete 75%)"),
      "very / really / incredibly"),
    R("hype", r"\b(?:absolutely|completely|totally|utterly|entirely|thoroughly)\s+(?=\w)", X, "absolutely"),
    R("hype", r"\b(?:definitely|certainly|undoubtedly|unquestionably|surely)\s+", X, "definitely"),
    R("hype", r"\b(?:notably|importantly|crucially|significantly|interestingly)[,]\s+", X, "Notably,"),
    R("hype", r"\bcutting[- ]edge\b", X, "cutting-edge"),
    R("hype", r"\bstate[- ]of[- ]the[- ]art\b", X, "state-of-the-art"),
    R("hype", r"\bnext[- ]gen(?:eration)?\b", X, "next-generation"),
    R("hype", r"\bworld[- ]class\b", X, "world-class"),
    R("hype", r"\bindustry[- ]leading\b", X, "industry-leading"),
    R("hype", r"\b(?:revolutionary|groundbreaking|transformative|unparalleled|unprecedented)\s+", X,
      "revolutionary / groundbreaking"),
    R("hype", r"\brobust(?:ly)?\b", ("solid", "sturdy", "reliable"), "robust"),
    R("hype", r"\bseamless\b", ("smooth", "clean"), "seamless"),
    R("hype", r"\bseamlessly\b", "smoothly", "seamlessly"),
    R("hype", r"\beffortless\b", "easy", "effortless"),
    R("hype", r"\beffortlessly\b", "easily", "effortlessly"),
    R("hype", r"\bcomprehensive(?:ly)?\b", ("full", "complete", "thorough"), "comprehensive"),
    R("hype", r"\bmeticulous\b", ("careful", "precise"), "meticulous"),
    R("hype", r"\bmeticulously\b", "carefully", "meticulously"),
    R("hype", r"\bintricate\b", ("complex", "detailed", "involved"), "intricate"),
    R("hype", r"\bprofound(?:ly)?\b", "deep", "profound"),
    R("hype", r"\b(?:crucial|pivotal|paramount)\b", ("key", "central", "main"), "crucial / pivotal"),
    R("hype", r"\binvaluable\b", ("useful", "handy"), "invaluable"),
    *V("hype", ("supercharge", "supercharges", "supercharged", "supercharging"),
               ("speed up", "speeds up", "sped up", "speeding up")),
    *V("hype", ("elevate", "elevates", "elevated", "elevating"),
               ("improve", "improves", "improved", "improving")),
    # documented "AI vocabulary" spikes after 2022 (WP:AIVOCAB)
    R("hype", r"\bvibrant\b", ("lively", "bright"), "vibrant"),
    R("hype", r"\benduring\b", ("lasting", "durable"), "enduring"),
    R("hype", r"\brenowned\b", "well-known", "renowned"),
    R("hype", r"\bvaluable\b", "useful", "valuable"),
    R("hype", r"\bbreathtaking\b", X, "breathtaking"),
    *V("hype", ("bolster", "bolsters", "bolstered", "bolstering"),
               ("boost", "boosts", "boosted", "boosting")),

    # -- wordy: long word, short word ---------------------------------------
    *V("wordy", ("utilize", "utilizes", "utilized", "utilizing"),
               (("use", "rely on"), ("uses", "relies on"),
                ("used", "relied on"), ("using", "relying on"))),
    R("wordy", r"\butiliz(?:ation|ations)\b", "use", "utilization"),
    *V("wordy", ("leverage", "leverages", "leveraged", "leveraging"),
               (("use", "draw on"), ("uses", "draws on"),
                ("used", "drew on"), ("using", "drawing on"))),
    *V("wordy", ("facilitate", "facilitates", "facilitated", "facilitating"),
               ("help", "helps", "helped", "helping")),
    *V("wordy", ("endeavor", "endeavors", "endeavored", "endeavoring"),
               ("try", "tries", "tried", "trying")),
    *V("wordy", ("endeavour", "endeavours", "endeavoured", "endeavouring"),
               ("try", "tries", "tried", "trying")),
    R("wordy", r"\bascertain\b", "find out", "ascertain"),
    *V("wordy", ("commence", "commences", "commenced", "commencing"),
               ("start", "starts", "started", "starting")),
    *V("wordy", ("initiate", "initiates", "initiated", "initiating"),
               ("start", "starts", "started", "starting")),
    *V("wordy", ("terminate", "terminates", "terminated", "terminating"),
               ("end", "ends", "ended", "ending")),
    *V("wordy", ("demonstrate", "demonstrates", "demonstrated", "demonstrating"),
               ("show", "shows", "showed", "showing")),
    # bare "underscore" and "highlight" are left alone: one is a character,
    # the other an ordinary imperative ("Highlight the row")
    *V("wordy", (None, "underscores", "underscored", "underscoring"),
               (None, "shows", "showed", "showing")),
    *V("wordy", ("showcase", "showcases", "showcased", "showcasing"),
               ("show", "shows", "showed", "showing")),
    *V("wordy", (None, "highlights", "highlighted", "highlighting"),
               (None, "shows", "showed", "showing")),
    *V("wordy", ("emphasize", "emphasizes", "emphasized", "emphasizing"),
               ("stress", "stresses", "stressed", "stressing")),
    *V("wordy", ("enhance", "enhances", "enhanced", "enhancing"),
               ("improve", "improves", "improved", "improving")),
    R("wordy", r"\benhancements?\b", "improvement", "enhancement"),
    *V("wordy", ("foster", "fosters", "fostered", "fostering"),
               ("build", "builds", "built", "building")),
    *V("wordy", ("garner", "garners", "garnered", "garnering"),
               ("get", "gets", "got", "getting")),
    R("wordy", r"\baligned with\b", "matched", "aligned with"),
    R("wordy", r"\baligning with\b", "matching", "aligning with"),
    R("wordy", r"\baligns with\b", "matches", "aligns with"),
    R("wordy", r"\balign with\b", "match", "align with"),
    R("wordy", r"\binterplay\b", "interaction", "interplay"),
    R("wordy", r"\bexemplifies\b", "shows", "exemplify"),
    R("wordy", r"\bnumerous\b", ("many", "plenty of"), "numerous"),
    R("wordy", r"\bmyriad(?: of)?\b", "many", "myriad"),
    R("wordy", r"\ba plethora of\b", "many", "a plethora of"),
    R("wordy", r"\ba multitude of\b", "many", "a multitude of"),
    R("wordy", r"\ban abundance of\b", "plenty of", "an abundance of"),
    R("wordy", r"\ba wealth of\b", "plenty of", "a wealth of"),
    R("wordy", r"\bsubstantial\b", ("large", "big", "sizable"), "substantial"),
    R("wordy", r"\bconsiderable\b", ("large", "big"), "considerable"),
    R("wordy", r"\bapproximately\b", ("about", "roughly", "around"), "approximately"),
    R("wordy", r"\bsufficient\b", "enough", "sufficient"),
    R("wordy", r"\badditional\b", ("more", "extra"), "additional"),
    *V("wordy", ("assist", "assists", "assisted", "assisting"),
               (("help", "support"), ("helps", "supports"),
                ("helped", "supported"), ("helping", "supporting"))),
    R("wordy", r"\battempts to\b", "tries to", "attempts to"),
    R("wordy", r"\battempt to\b", "try to", "attempt to"),
    *V("wordy", ("obtain", "obtains", "obtained", "obtaining"),
               ("get", "gets", "got", "getting")),
    *V("wordy", ("acquire", "acquires", "acquired", "acquiring"),
               ("get", "gets", "got", "getting")),
    *V("wordy", ("necessitate", "necessitates", "necessitated", "necessitating"),
               ("need", "needs", "needed", "needing")),
    *V("wordy", ("permit", "permits", "permitted", "permitting"),
               ("let", "lets", "let", "letting")),
    *V("wordy", ("ensure", "ensures", "ensured", "ensuring"),
               ("make sure", "makes sure", "made sure", "making sure")),
    R("wordy", r"\bmethodolog(?:y|ies)\b", "method", "methodology"),
    R("wordy", r"\boptim(?:al|um)\b", "best", "optimal"),
    R("wordy", r"\bcurrently\b", "now", "currently"),
    R("wordy", r"\bpresently\b", "now", "presently"),
    R("wordy", r"\bfrequently\b", ("often", "regularly"), "frequently"),
    R("wordy", r"\boccasionally\b", ("sometimes", "now and then"), "occasionally"),
    R("wordy", r"\btypically\b", ("usually", "normally", "generally"), "typically"),
    R("wordy", r"\bregarding\b", "about", "regarding"),
    R("wordy", r"\b(?:basically|essentially|literally|actually|simply)\s+", X, "basically / essentially"),

    # -- contractions: the formal register LLMs default into ----------------
    # Avoiding contractions is one of the loudest tells, and contracting
    # changes nothing about meaning. Negations first, so "it is not" lands on
    # "it's not" rather than "it isn't".
    R("contractions", r"\bdo not\b", contract("don't"), "do not"),
    R("contractions", r"\bdoes not\b", contract("doesn't"), "does not"),
    R("contractions", r"\bdid not\b", contract("didn't"), "did not"),
    R("contractions", r"\bis not\b", contract("isn't"), "is not"),
    R("contractions", r"\bare not\b", contract("aren't"), "are not"),
    R("contractions", r"\bwas not\b", contract("wasn't"), "was not"),
    R("contractions", r"\bwere not\b", contract("weren't"), "were not"),
    R("contractions", r"\bcan ?not\b", contract("can't"), "cannot"),
    R("contractions", r"\bwill not\b", contract("won't"), "will not"),
    R("contractions", r"\bwould not\b", contract("wouldn't"), "would not"),
    R("contractions", r"\bshould not\b", contract("shouldn't"), "should not"),
    R("contractions", r"\bcould not\b", contract("couldn't"), "could not"),
    R("contractions", r"\bhas not\b", contract("hasn't"), "has not"),
    R("contractions", r"\bhave not\b", contract("haven't"), "have not"),
    R("contractions", r"\bhad not\b", contract("hadn't"), "had not"),
    R("contractions", r"\bit is\b(?=\s+[\w\x00])", contract("it's"), "it is"),
    R("contractions", r"\bthat is\b(?!,)(?=\s+[\w\x00])", contract("that's"), "that is"),
    R("contractions", r"\bthere is\b(?=\s+[\w\x00])", contract("there's"), "there is"),
    R("contractions", r"\bhere is\b(?=\s+[\w\x00])", contract("here's"), "here is"),
    R("contractions", r"\bwhat is\b(?=\s+[\w\x00])", contract("what's"), "what is"),
    R("contractions", r"\byou are\b(?=\s+[\w\x00])", contract("you're"), "you are"),
    R("contractions", r"\bwe are\b(?=\s+[\w\x00])", contract("we're"), "we are"),
    R("contractions", r"\bthey are\b(?=\s+[\w\x00])", contract("they're"), "they are"),
    R("contractions", r"\bi am\b(?=\s+[\w\x00])", contract("I'm"), "I am"),
    R("contractions", r"\byou will\b(?=\s+[\w\x00])", contract("you'll"), "you will"),
    R("contractions", r"\bwe will\b(?=\s+[\w\x00])", contract("we'll"), "we will"),
    R("contractions", r"\bit will\b(?=\s+[\w\x00])", contract("it'll"), "it will"),
    R("contractions", r"\bthey will\b(?=\s+[\w\x00])", contract("they'll"), "they will"),
    R("contractions", r"\blet us\b(?=\s+[\w\x00])", contract("let's"), "let us"),
    # have/has only contract as auxiliaries. "We have three options" must not
    # become "We've three options", so require a past participle after it.
    R("contractions", r"\byou have (?=" + PARTICIPLE + r"\b)", contract("you've "), "you have V-ed"),
    R("contractions", r"\bwe have (?=" + PARTICIPLE + r"\b)", contract("we've "), "we have V-ed"),
    R("contractions", r"\bthey have (?=" + PARTICIPLE + r"\b)", contract("they've "), "they have V-ed"),
    R("contractions", r"\bi have (?=" + PARTICIPLE + r"\b)", contract("I've "), "I have V-ed"),

    # -- punctuation: the glyphs that give it away --------------------------
    R("punctuation", r"[ \t]*—[ \t]*", em_dash, "em-dash"),
    R("punctuation", "[“”]", '"', "curly double quote"),
    R("punctuation", "[‘’]", "'", "curly quote / apostrophe"),
    R("punctuation", "…", "...", "ellipsis character"),
    # a horizontal rule sitting above a heading: Markdown habit, pure noise
    R("punctuation", r"(?m)^(?:-{3,}|\*{3,}|_{3,})[ \t]*\n\s*\n(?=#{1,6} )", X,
      "thematic break before heading"),

    # -- structure: flag only, the fix needs judgment -----------------------
    R("structure", r"\bnot just\b[^.!?\n]{0,80}?\bbut\b", FLAG, "not just X, but Y"),
    R("structure", r"\bnot only\b[^.!?\n]{0,80}?\bbut also\b", FLAG, "not only X but also Y"),
    R("structure", r"\bisn't (?:just )?about\b[^.!?\n]{0,60}?\bit's about\b", FLAG, "isn't about X, it's about Y"),
    R("structure", r"\b(?:this|it|that) (?:isn't|is not|wasn't)\b[^.!?\n]{0,60}[.!]\s+(?:it's|this is|that's)\b",
      FLAG, "negative parallelism: not X. Y."),
    R("structure", r"(?m)^\s*[-*]\s+\*\*[^*\n]+\*\*\s*[-:]", FLAG, "bold-lead bullet"),
    R("structure", r"\blet(?:'s| us)\b", FLAG, "let's (collaborative we)"),
    R("structure", r"\bwe(?:'ll| will|'ve| have)\b", FLAG, "we (when you mean you or I)"),
    R("structure", r"\bnot an? \w+[^.!?\n]{0,40}?\bbut (?:a|an|rather)\b", FLAG, "not a X but a Y"),
    R("structure", r"\bno \w+[^,\n]{0,30}, no \w+[^,\n]{0,30}, just\b", FLAG, "no X, no Y, just Z"),
    # a present participle bolted onto the end of a sentence, carrying a
    # claim about significance that nothing in the text supports
    R("structure", r",\s+(?:highlighting|showcasing|reflecting|underscoring|emphasizing|"
      r"demonstrating|illustrating|contributing|solidifying|cementing|fostering|embodying|"
      r"marking|serving|creating|offering|ensuring)\b[^.!?\n]{0,120}[.!?]",
      FLAG, "trailing -ing analysis"),
    # "adjective, adjective, and adjective" padding, narrowed to abstract
    # nouns so ordinary lists do not trip it
    R("structure", r"\b\w{4,}(?:ing|ity|ness|ance|ence|ment|tion), "
      r"\w{4,}(?:ing|ity|ness|ance|ence|ment|tion),? and "
      r"\w{4,}(?:ing|ity|ness|ance|ence|ment|tion)\b", FLAG, "rule of three (abstract nouns)"),
    R("structure", r"(?m)^#{1,6} +(?:[A-Z][a-z]+ ){2,}[A-Z][a-z]+[ \t]*$", FLAG, "title-case heading"),
    R("structure", r"\bdespite (?:its|their|these)\b[^.!?\n]{0,60}?\bfac(?:es|ing|e)\b",
      FLAG, "Despite its X, Y faces challenges"),

    # -- emoji: off by default, tables and checklists use them on purpose ---
    R("emoji", r"[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF←-⇿⌀-⏿"
      r"☀-➿⬀-⯿️‍]+\s?", X, "decorative emoji"),
]

CATEGORIES = []
for _r in RULES:
    if _r.cat not in CATEGORIES:
        CATEGORIES.append(_r.cat)

DEFAULT_ON = {"sycophancy", "filler", "closer", "cliche", "puffery", "copula", "chatbot",
              "corporate", "hype", "wordy", "punctuation", "contractions"}


# --- protecting code -------------------------------------------------------

MASKS = [
    re.compile(r"```.*?```", re.S),                        # fenced block
    re.compile(r"~~~.*?~~~", re.S),                        # fenced block, alt
    re.compile(r"`[^`\n]+`"),                              # inline code
    re.compile(r"(?m)^(?: {4,}|\t)(?![-*+ ]|\d+[.)])\S.*$"),  # indented code
    re.compile(r"<[^>\n]{1,200}>"),                        # html / jsx tag
    re.compile(r"\bhttps?://\S+"),                         # bare url
    re.compile(r"(?<=\])\([^)\n]*\)"),                     # markdown link target
    re.compile(r"(?m)^---$.*?^---$", re.S),                # yaml frontmatter
]


def mask(text):
    """Swap code-ish spans for placeholders so no rule can touch them."""
    store = []

    def take(m):
        store.append(m.group(0))
        return "\x00%d\x00" % (len(store) - 1)

    for pattern in MASKS:
        text = pattern.sub(take, text)
    return text, store


def unmask(text, store):
    return re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], text)


# --- rewriting -------------------------------------------------------------

def _match_case(src, dst):
    if not src or not dst or not dst[0].isalpha():
        return dst
    if src[0].isupper():
        return dst[0].upper() + dst[1:]
    return dst


def describe(rule):
    """One-line summary of what a rule does, for --list and --check."""
    if rule.repl is FLAG:
        return "(needs a human)"
    if callable(rule.repl):
        return CALLABLE_LABELS.get(rule.repl, "(context aware)")
    if isinstance(rule.repl, tuple):
        return " / ".join(rule.repl)
    if rule.repl in (X, CUT):
        return "(delete)"
    return rule.repl


def _active(enabled):
    if enabled is None:
        enabled = DEFAULT_ON
    return [r for r in RULES if r.cat in enabled and r.repl is not FLAG]


VOWEL_SOUND = {"hour", "honest", "honestly", "honor", "honour", "heir"}
CONSONANT_SOUND = {
    "one", "once", "user", "users", "unique", "unit", "units", "union", "universal",
    "university", "useful", "use", "uses", "usage", "utility", "uniform", "ubiquitous",
    "european", "euro", "url", "ui", "uuid",
}


def fix_articles(text):
    def swap(m):
        art, gap, word = m.group(1), m.group(2), m.group(3)
        low = word.lower()
        if word.isupper():
            return m.group(0)  # acronym, sounds vary, leave it
        vowel = low[0] in "aeiou"
        if low in CONSONANT_SOUND:
            vowel = False
        elif low in VOWEL_SOUND:
            vowel = True
        want = "an" if vowel else "a"
        return _match_case(art, want) + gap + word

    return re.sub(r"\b([Aa]n?)([ \t]+)([A-Za-z]+)", swap, text)


def tidy(text):
    """Clean up the holes the deletions leave behind."""
    # CUT marker: capitalize whatever sentence now starts here
    text = re.sub(r"\x01\s*([a-z])", lambda m: m.group(1).upper(), text)
    text = text.replace("\x01", "")
    text = re.sub(r"(?<=\S)[ \t]{2,}", " ", text)      # doubled spaces, not indents
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)    # space before punctuation
    text = re.sub(r"(?m)[ \t]+$", "", text)            # trailing space
    text = re.sub(r"\n{3,}", "\n\n", text)             # runaway blank lines
    return text


def scrub(text, enabled=None, articles=True):
    """Rewrite text. Returns (new_text, {rule_note: count})."""
    masked, store = mask(text)
    counts = {}
    for rule in _active(enabled):
        if callable(rule.repl):
            new, n = rule.pat.subn(rule.repl, masked)
        elif isinstance(rule.repl, tuple):
            new, n = rule.pat.subn(
                lambda m, r=rule: _match_case(m.group(0), pick(r.repl, m)), masked)
        elif rule.repl in (X, CUT):
            new, n = rule.pat.subn(rule.repl, masked)
        else:
            new, n = rule.pat.subn(
                lambda m, r=rule: _match_case(m.group(0), r.repl), masked)
        # count edits, not matches: a rule that fires but leaves the text
        # alone (a kept "very", a shouted "DO NOT") did not change anything
        if new != masked:
            counts[rule.note] = counts.get(rule.note, 0) + n
        masked = new
    masked = tidy(masked)
    if articles:
        masked = fix_articles(masked)
    return unmask(masked, store), counts


def analyze(text, enabled=None):
    """Find every hit without changing anything. Returns a list of dicts."""
    if enabled is None:
        enabled = DEFAULT_ON | {"structure"}
    masked, _ = mask(text)
    hits = []
    for rule in RULES:
        if rule.cat not in enabled:
            continue
        for m in rule.pat.finditer(masked):
            hits.append({
                "line": masked.count("\n", 0, m.start()) + 1,
                "cat": rule.cat,
                "note": rule.note,
                "text": " ".join(m.group(0).split())[:60],
                "fix": describe(rule),
            })
    hits.sort(key=lambda h: h["line"])
    return hits


# --- cli -------------------------------------------------------------------

def resolve(on, off):
    enabled = set(DEFAULT_ON)
    for c in on or []:
        if c == "all":
            enabled |= set(CATEGORIES)
        else:
            enabled.add(c)
    for c in off or []:
        enabled.discard(c)
    return enabled


def main(argv=None):
    p = argparse.ArgumentParser(description="Strip LLM tics from text.")
    p.add_argument("files", nargs="*", help="files to process; default stdin")
    p.add_argument("--check", action="store_true", help="report hits, change nothing")
    p.add_argument("--in-place", "-i", action="store_true", help="rewrite files on disk")
    p.add_argument("--on", action="append", metavar="CAT", help="enable a category, or 'all'")
    p.add_argument("--off", action="append", metavar="CAT", help="disable a category")
    p.add_argument("--no-articles", action="store_true", help="skip a/an repair")
    p.add_argument("--list", action="store_true", help="print the rule database")
    p.add_argument("--selftest", action="store_true", help="run built-in tests")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.list:
        for cat in CATEGORIES:
            rules = [r for r in RULES if r.cat == cat]
            state = "on" if cat in DEFAULT_ON else "off"
            print("\n%s (%d rules, %s by default)" % (cat, len(rules), state))
            for r in rules:
                print("  %-42s %s" % (r.note, describe(r)))
        return 0

    enabled = resolve(args.on, args.off)
    unknown = enabled - set(CATEGORIES)
    if unknown:
        p.error("unknown category: %s (have: %s)" % (", ".join(sorted(unknown)), ", ".join(CATEGORIES)))

    sources = args.files or ["-"]
    if args.in_place and "-" in sources:
        p.error("--in-place needs file arguments")

    found = 0
    for path in sources:
        text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()

        if args.check:
            for h in analyze(text, enabled | {"structure"}):
                found += 1
                print("%s:%d  %-11s %-34s %s" % (path, h["line"], h["cat"], h["text"], h["fix"]))
            continue

        out, counts = scrub(text, enabled, articles=not args.no_articles)
        found += sum(counts.values())
        if args.in_place:
            if out != text:
                open(path, "w", encoding="utf-8").write(out)
            print("%s: %d rewrites" % (path, sum(counts.values())), file=sys.stderr)
        else:
            sys.stdout.write(out)

    return 1 if (args.check and found) else 0


# --- tests -----------------------------------------------------------------

CASES = [
    ("That's a great question! The answer is 42.", "The answer is 42."),
    ("You're absolutely right, the path is wrong.", "The path is wrong."),
    ("It's important to note that the file is missing.", "The file is missing."),
    ("We utilize a robust framework to facilitate this.",
     "We rely on a sturdy framework to help this."),
    ("Let's delve into the realm of caching.", "Let's dig into caching."),
    ("This is a very robust and incredibly seamless solution.",
     "This is a sturdy and clean solution."),
    ("In order to run it, use the flag.", "To run it, use the flag."),
    ("I hope this helps! Let me know if you have questions.", ""),
    ("Use `leverage` and utilize it.", "Use `leverage` and rely on it."),
    ("```py\nx = utilize()\n```", "```py\nx = utilize()\n```"),
    ("It offers an abundance of options.", "It offers plenty of options."),
    ("A comprehensive guide.", "A complete guide."),
    ("Due to the fact that it failed, we stopped.", "Because it failed, we stopped."),
    ("First and foremost, check the logs.", "First, check the logs."),
    ("See https://example.com/utilize-this for more.",
     "See https://example.com/utilize-this for more."),
    # em-dash
    ("We ship it — soon.", "We ship it, soon."),
    ("The fix — a one-liner — landed.", "The fix, a one-liner, landed."),
    ("It is fast—cheap too.", "It's fast, cheap too."),
    ("The range 1914—1918 held.", "The range 1914—1918 held."),
    ("Quote.\n— Anonymous", "Quote.\n— Anonymous"),
    ("Wait, — that is wrong.", "Wait, that's wrong."),
    ("Use `a — b` verbatim.", "Use `a — b` verbatim."),
    # from Wikipedia:Signs of AI writing
    ("The library boasts a clean API.", "The library has a clean API."),
    ("The cache serves as a buffer.", "The cache is a buffer."),
    ("Nestled in the heart of the repo.", "In the repo."),
    ("It underscores its importance for users.", "It matters for users."),
    ("The town faces several challenges.", "The town has problems."),
    ("Additionally, the flag is optional.", "Also, the flag is optional."),
    ("It garnered praise and enduring support.", "It got praise and lasting support."),
    ("As of my last knowledge update, this is unknown.", "This is unknown."),
    ("The details aren't widely documented.", "The details are unclear."),
    ("The date isn't widely documented.", "The date is unclear."),
    ("Say “hello” and it’s done…", "Say \"hello\" and it's done..."),
    # verb agreement: the replacement has to match the form it replaces
    ("This demonstrates the bug.", "This shows the bug."),
    ("The report highlights three issues.", "The report shows three issues."),
    ("Highlight the selected row.", "Highlight the selected row."),
    ("Use an underscore in the name.", "Use an underscore in the name."),
    # contractions
    ("It is not a bug.", "It isn't a bug."),
    ("You are correct and we cannot ship.", "You're correct and we can't ship."),
    ("We have seen this before.", "We've seen this before."),
    ("We have three options.", "We have three options."),   # main verb, not auxiliary
    ("DO NOT delete this.", "DO NOT delete this."),          # shouted, so left alone
    # a stranded copula cannot contract
    ("The plan — such as it is — ships Friday.", "The plan, such as it is, ships Friday."),
    ("Here it is.", "Here it is."),
    ("Yes, we are.", "Yes, we are."),
    # rotation: two words that both map to "use" must not both become "use".
    # These also pin the hash, so a switch to Python's salted hash() would fail.
    ("We utilize the cache and leverage the index.",
     "We rely on the cache and use the index."),
    ("A robust design, a robust parser, and robust tooling.",
     "A solid design, a reliable parser, and solid tooling."),
]


def selftest():
    bad = 0
    for src, want in CASES:
        got, _ = scrub(src)
        got = got.strip()
        if got != want:
            bad += 1
            print("FAIL  in:   %r" % src)
            print("      want: %r" % want)
            print("      got:  %r" % got)
    flags = analyze("It's not just fast, but cheap.", {"structure"})
    if not flags:
        bad += 1
        print("FAIL  structure rule did not flag 'not just X but Y'")
    print("%d/%d passed" % (len(CASES) + 1 - bad, len(CASES) + 1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
