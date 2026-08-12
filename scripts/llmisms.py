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
import re
import sys

# --- replacement markers ---------------------------------------------------

X = ""        # delete outright, for mid-sentence words
CUT = "\x01"  # delete and capitalize whatever follows, for sentence openers
FLAG = None   # report only, never rewrite

CAPFIX = "\x01"


class Rule:
    __slots__ = ("cat", "pat", "repl", "note")

    def __init__(self, cat, pattern, repl, note):
        self.cat = cat
        self.pat = re.compile(pattern, re.IGNORECASE)
        self.repl = repl
        self.note = note


def R(cat, pattern, repl, note):
    return Rule(cat, pattern, repl, note)


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
      r"exceptionally|tremendously|immensely)\s+", X, "very / really / incredibly"),
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
    R("hype", r"\brobust(?:ly)?\b", "solid", "robust"),
    R("hype", r"\bseamless\b", "smooth", "seamless"),
    R("hype", r"\bseamlessly\b", "smoothly", "seamlessly"),
    R("hype", r"\beffortless\b", "easy", "effortless"),
    R("hype", r"\beffortlessly\b", "easily", "effortlessly"),
    R("hype", r"\bcomprehensive(?:ly)?\b", "full", "comprehensive"),
    R("hype", r"\bmeticulous\b", "careful", "meticulous"),
    R("hype", r"\bmeticulously\b", "carefully", "meticulously"),
    R("hype", r"\bintricate\b", "complex", "intricate"),
    R("hype", r"\bprofound(?:ly)?\b", "deep", "profound"),
    R("hype", r"\b(?:crucial|pivotal|paramount)\b", "key", "crucial / pivotal"),
    R("hype", r"\binvaluable\b", "useful", "invaluable"),
    R("hype", r"\bsupercharge(?:s|d)?\b", "speed up", "supercharge"),
    R("hype", r"\belevates?\b", "improve", "elevate"),

    # -- wordy: long word, short word ---------------------------------------
    R("wordy", r"\butiliz(?:e|es)\b", "use", "utilize"),
    R("wordy", r"\butilized\b", "used", "utilized"),
    R("wordy", r"\butilizing\b", "using", "utilizing"),
    R("wordy", r"\butilization\b", "use", "utilization"),
    R("wordy", r"\bleverag(?:e|es)\b", "use", "leverage"),
    R("wordy", r"\bleveraged\b", "used", "leveraged"),
    R("wordy", r"\bleveraging\b", "using", "leveraging"),
    R("wordy", r"\bfacilitates?\b", "help", "facilitate"),
    R("wordy", r"\bendeavou?rs?\b", "try", "endeavor"),
    R("wordy", r"\bascertain\b", "find out", "ascertain"),
    R("wordy", r"\bcommences?\b", "start", "commence"),
    R("wordy", r"\binitiates?\b", "start", "initiate"),
    R("wordy", r"\bterminates?\b", "end", "terminate"),
    R("wordy", r"\bdemonstrates?\b", "show", "demonstrate"),
    R("wordy", r"\bunderscores?\b", "shows", "underscore"),
    R("wordy", r"\bshowcases?\b", "show", "showcase"),
    R("wordy", r"\bexemplifies\b", "shows", "exemplify"),
    R("wordy", r"\bnumerous\b", "many", "numerous"),
    R("wordy", r"\bmyriad(?: of)?\b", "many", "myriad"),
    R("wordy", r"\ba plethora of\b", "many", "a plethora of"),
    R("wordy", r"\ba multitude of\b", "many", "a multitude of"),
    R("wordy", r"\ban abundance of\b", "plenty of", "an abundance of"),
    R("wordy", r"\ba wealth of\b", "plenty of", "a wealth of"),
    R("wordy", r"\bsubstantial\b", "large", "substantial"),
    R("wordy", r"\bconsiderable\b", "large", "considerable"),
    R("wordy", r"\bapproximately\b", "about", "approximately"),
    R("wordy", r"\bsufficient\b", "enough", "sufficient"),
    R("wordy", r"\badditional\b", "more", "additional"),
    R("wordy", r"\bassists?\b", "help", "assist"),
    R("wordy", r"\battempts? to\b", "try to", "attempt to"),
    R("wordy", r"\bobtains?\b", "get", "obtain"),
    R("wordy", r"\bacquires?\b", "get", "acquire"),
    R("wordy", r"\bnecessitates?\b", "need", "necessitate"),
    R("wordy", r"\bpermits?\b", "let", "permit"),
    R("wordy", r"\bensures?\b", "make sure", "ensure"),
    R("wordy", r"\bmethodolog(?:y|ies)\b", "method", "methodology"),
    R("wordy", r"\boptim(?:al|um)\b", "best", "optimal"),
    R("wordy", r"\bcurrently\b", "now", "currently"),
    R("wordy", r"\bpresently\b", "now", "presently"),
    R("wordy", r"\bfrequently\b", "often", "frequently"),
    R("wordy", r"\boccasionally\b", "sometimes", "occasionally"),
    R("wordy", r"\btypically\b", "usually", "typically"),
    R("wordy", r"\bregarding\b", "about", "regarding"),
    R("wordy", r"\b(?:basically|essentially|literally|actually|simply)\s+", X, "basically / essentially"),

    # -- structure: flag only, the fix needs judgment -----------------------
    R("structure", r"\bnot just\b[^.!?\n]{0,80}?\bbut\b", FLAG, "not just X, but Y"),
    R("structure", r"\bnot only\b[^.!?\n]{0,80}?\bbut also\b", FLAG, "not only X but also Y"),
    R("structure", r"\bisn't (?:just )?about\b[^.!?\n]{0,60}?\bit's about\b", FLAG, "isn't about X, it's about Y"),
    R("structure", r"\b(?:this|it|that) (?:isn't|is not|wasn't)\b[^.!?\n]{0,60}[.!]\s+(?:it's|this is|that's)\b",
      FLAG, "negative parallelism: not X. Y."),
    R("structure", r"—", FLAG, "em-dash"),
    R("structure", r"(?m)^\s*[-*]\s+\*\*[^*\n]+\*\*\s*[-:]", FLAG, "bold-lead bullet"),
    R("structure", r"\blet(?:'s| us)\b", FLAG, "let's (collaborative we)"),
    R("structure", r"\bwe(?:'ll| will|'ve| have)\b", FLAG, "we (when you mean you or I)"),

    # -- emoji: off by default, tables and checklists use them on purpose ---
    R("emoji", r"[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF←-⇿⌀-⏿"
      r"☀-➿⬀-⯿️‍]+\s?", X, "decorative emoji"),
]

CATEGORIES = []
for _r in RULES:
    if _r.cat not in CATEGORIES:
        CATEGORIES.append(_r.cat)

DEFAULT_ON = {"sycophancy", "filler", "closer", "cliche", "corporate", "hype", "wordy"}


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
        if rule.repl in (X, CUT):
            masked, n = rule.pat.subn(rule.repl, masked)
        else:
            masked, n = rule.pat.subn(
                lambda m, r=rule: _match_case(m.group(0), r.repl), masked)
        if n:
            counts[rule.note] = counts.get(rule.note, 0) + n
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
                "fix": "(needs a human)" if rule.repl is FLAG
                       else "(delete)" if rule.repl in (X, CUT) else rule.repl,
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
                fix = "FLAG" if r.repl is FLAG else "delete" if r.repl in (X, CUT) else "-> " + r.repl
                print("  %-42s %s" % (r.note, fix))
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
     "We use a solid framework to help this."),
    ("Let's delve into the realm of caching.", "Let's dig into caching."),
    ("This is a very robust and incredibly seamless solution.",
     "This is a solid and smooth solution."),
    ("In order to run it, use the flag.", "To run it, use the flag."),
    ("I hope this helps! Let me know if you have questions.", ""),
    ("Use `leverage` and utilize it.", "Use `leverage` and use it."),
    ("```py\nx = utilize()\n```", "```py\nx = utilize()\n```"),
    ("It offers an abundance of options.", "It offers plenty of options."),
    ("A comprehensive guide.", "A full guide."),
    ("Due to the fact that it failed, we stopped.", "Because it failed, we stopped."),
    ("First and foremost, check the logs.", "First, check the logs."),
    ("See https://example.com/utilize-this for more.",
     "See https://example.com/utilize-this for more."),
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
