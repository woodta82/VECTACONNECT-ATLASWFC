# Attribution evaluation: people_cases_heldout2

Run at 2026-10-28T15:02:24+00:00.

**Provenance.** AUTHORED second held-out set, written on 28 Oct 2026 after the rule changes that followed the first held-out run, and run ONCE without changing any rule afterwards. Every organisation and person is invented. Authored text, not genuine documents: it does not measure real-world accuracy.

| Measure | Result |
|---|---|
| Cases read | 12 (not read: 0) |
| People found (precision) | 11/11 (100%) |
| People expected (recall) | 11/13 (85%) |
| Title bindings correct (recall) | 10/11 (91%) |
| Current/former/incoming correct | 10/10 (100%) |
| Organisation bindings correct (recall) | 9/10 (90%) |
| Unsupported associations kept unresolved | 5/5 (100%) |
| Wrong bindings (a title or organisation the document does not give) | 0 |

## Cases

- **g01-two-appointments**: correct
- **g02-gssa-quote**: correct
- **g03-former-employer-mention**: correct
- **g04-tender-contact-block**: Samuel Kiptoo: title 'Head of Procurement' not bound; Samuel Kiptoo: organisation 'Example Port Authority' not bound
- **g05-ceo-said-org-later**: correct
- **g06-chair-of-board**: correct
- **g07-retired-former**: correct
- **g08-partner-org-apposition**: correct
- **g09-listing-dash**: correct
- **g10-no-binding-attendees**: correct
- **g11-interim**: correct
- **g12-is-role-at**: correct

## Correction (added after the run, same day)

The evaluator used for this run counted a title or organisation as "not bound" but did not count a *different* one that
was bound. Diagnosis of case g04 showed the rules had bound the title **'Head'** and the organisation **'Procurement'**
("Samuel Kiptoo, Head of Procurement, Example Port Authority"). Strictly counted, this run had **1 wrong binding**, not 0.
The rule was then corrected (after "of"/"for", a capitalised phrase stays part of the title unless it is a known
organisation or reads as one), the evaluator now counts conflicting bindings, and this set is no longer held out.
