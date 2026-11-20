# NeoAddressMatcher: Intelligent UK Address Matching

Matching real-world UK addresses to official UPRN property records is notoriously difficult. People abbreviate, type phonetically, skip lines, omit house numbers on named cottages, or write `"Flat 1, 14"` when the official record says `"14A"`.

**NeoAddressMatcher** doesn't just compare text—it **understands how UK addresses work**.

---

## Why Traditional Matchers Fail: "The Neighbour Trap"

To a standard text-matching tool, **`12 High Street, Guildford, GU1 3AA`** and **`14 High Street, Guildford, GU1 3AA`** are **97% identical** (only one digit differs). Standard tools happily match your customer to their next-door neighbour.

**How NeoAddressMatcher handles it:**
- It separates the **property identity** (flat, house name, house number) from the **location** (street, town, postcode).
- If the house or flat number contradicts the official record, it applies an automatic **conflict brake**—scoring `14 High Street` at **100%** while dropping next-door `12 High Street` below **45% (Low / No Match)**.

---

## "Wow" Edge Cases It Catches Automatically

| Real-World Problem | What the Customer Typed | Official UPRN Record | Result & Why It Works |
| :--- | :--- | :--- | :--- |
| **UK Flat & Door-Letter Equivalents** | `Flat 1, 14 High St` *(or `Ground Floor Flat, 14 High St`)* | `14A High Street` | **96% Match** — Knows `Flat 1` / `Flat A` / `Ground Floor` on `#14` is the same door as `14A`. |
| **House Name vs. House Number** | `Rose Cottage, High Street` *(omitted `#14`)* **or** `14 High Street` *(omitted `Rose Cottage`)* | `Rose Cottage, 14 High Street` | **94% Match** — Recognizes dual-named UK properties when only the name or number is given, while rejecting `Ivy Cottage, 14 High St`. |
| **Spelled How It Sounds (UK Phonetics)** | `14 Beecham Pl, Lester` | `14 Beauchamp Place, Leicester` | **92% Match** — Built-in British phonetic engine understands silent letters (`Beauchamp`, `Leicester`, `Marylebone`, `Chiswick`, `Greenwich`). |
| **"St." (Saint) vs. "St." (Street) & Ranges** | `Fourteen St. John's St.` | `12-16 Saint Johns Street` | **93% Match** — Knows the first `St.` is *Saint*, the second `St.` is *Street*, `Fourteen` is `14`, and `14` belongs inside the even range `12-16`. |
| **Jumbled & Shifted Address Lines** | **Line 1:** `Flat 2, Sovereign Ct, 14 High St`<br>**Line 2:** *(blank)*<br>**Line 3:** `Guildford` | **Line 1:** `Flat 2`<br>**Line 2:** `Sovereign Court, 14 High Street`<br>**Line 3:** `Guildford, Surrey` | **99% Match** — Reads across all lines so shifted fields and optional counties (`Surrey`, `Hants`, `Berks`) never hurt the score. |
| **Messy, Missing, or Scanned Postcodes** | `sw1a2aa` *(no space)*, `5WIA 2AA` *(scanner typos)*, or postcode typed inside Line 3 | `SW1A 2AA` | **95%–100% Match** — Fixes spacing/case, repairs `5↔S`, `I↔1`, `0↔O` scanner mistakes, and rescues postcodes typed in the wrong box. |
| **London Boroughs vs. "London"** | `221B Baker St, Marylebone, Westminster` | `221B Baker Street, London` | **98% Match** — Knows `Westminster`, `Camden`, `Hackney`, etc. are valid London equivalents to the Royal Mail `"LONDON"` post town. |
| **Scottish & Welsh Property Formats** | `Flat 2F1, 14 Sauchiehall St` **or** `Ty Gwyn, 12 Heol-y-Bont` | `2/1, 14 Sauchiehall Street` **or** `Ty Gwyn, 12 Heol Y Bont` | **95%+ Match** — Understands Scottish tenement codes (`2F1` = `2nd Floor, Flat 1` = `2/1`) and Welsh street terms (`Heol`, `Ffordd`, `Ty`). |

---

## Built-In Safety & Transparency

1. **Dynamic Intelligence**:
   - In rural villages where houses have names instead of numbers (e.g. *The Old Rectory, Church Lane*), the matcher automatically shifts its focus onto the house name so rural addresses score just as accurately as city streets.
2. **Automatic Ambiguity Alerts**:
   - If a customer enters `14 High Street` without a flat number, and the official database shows `14 High Street` is divided into `Flat 1` and `Flat 2`, the matcher **flags the result as Ambiguous** rather than blindly guessing the wrong flat.
3. **Clear Confidence Tiers & Audit Trail**:
   - Every match returns a clear rating (**Exact**, **High**, **Medium**, **Low**, or **No Match**) alongside an itemized scorecard showing how the Postcode, House Number, Flat, Building Name, Street, and Town each contributed to the final decision.
4. **Zero Setup Required**:
   - Runs as a single, self-contained Python function with **zero external software dependencies**, capable of screening thousands of candidate properties in a fraction of a second.
