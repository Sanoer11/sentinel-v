"""
Step 2b scenarios: whole radio sequences, spoken by Timbre voices, heard by Prisma, judged by the engine.

Each step: (t seconds, channel, speaker, text). Speakers map to fixed voices so every aircraft
sounds like one person. `expect` lists alerts that MUST appear at a step (index into steps);
`no_red` means the scenario is normal traffic and any RED is a false alarm.

Real events replayed (names as they were; Vistara merged into Air India in Nov 2024):
  DEL_2023  Delhi 23 Aug 2023: VTI926 told to cross 29R while VTI725 was cleared for take-off on 29R.
  BOM_2024  Mumbai 8 Jun 2024: IndiGo 6053 cleared to land on 27 while Air India 657 was taking off on 27.
Constructed (the failure types those incidents belong to):
  HOLD_AS_CROSS   hold-short read back as "crossing" while the runway is in use
  TWIN_CALLSIGN   IFLY 5124 takes the landing clearance meant for IFLY 5134
  STOP            stop immediately during a take-off clearance
  BIRDS_MR        Bird Chaser reports birds (Marathi) on a runway with a departure cleared
  VEHICLE_HI      Follow Me asks (Hinglish) to cross a runway an aircraft is cleared to land on
  NORMAL_DEL      a normal Delhi sequence: must give NO red alert
"""

VOICE = {   # speaker -> (voice, model, lang). Dev voices only; the locked-exam voices stay unseen.
    "tower": ("Avinash", "timbre-v3.0", "en-IN"),
    "p1": ("Riyaa", "timbre-v3.0", "en-IN"),
    "p2": ("Harshad", "timbre-v3.0", "en-IN"),
    "p3": ("Prakash", "timbre-v3.0", "en-IN"),
    "veh_mr": ("Zahira", "timbre-v2.5", "mr-IN"),
    "veh_hi": ("Poorvi", "timbre-v2.5", "hi-en"),
}

SCENARIOS = {
    "DEL_2023": dict(airport="VIDP", traffic=["VTI725", "VTI926", "AIC2817"],
                     phases={"VTI725": "ground", "VTI926": "ground"},
                     steps=[(0, "tower", "tower", "Vistara seven two five, runway two niner right, cleared for takeoff."),
                            (4, "pilot", "p1", "Runway two niner right, cleared for takeoff, Vistara seven two five."),
                            (25, "tower", "tower", "Vistara niner two six, cross runway two niner right."),
                            (29, "pilot", "p2", "Crossing runway two niner right, Vistara niner two six.")],
                     expect=[(2, "RUNWAY_CONFLICT", "RED")]),
    "BOM_2024": dict(airport="VABB", traffic=["AIC657", "IGO6053", "AKJ1123"],
                     phases={"AIC657": "ground", "IGO6053": "air"},
                     steps=[(0, "tower", "tower", "Air India six five seven, runway two seven, cleared for takeoff."),
                            (4, "pilot", "p1", "Runway two seven, cleared for takeoff, Air India six five seven."),
                            (40, "tower", "tower", "IFLY six zero five tree, runway two seven, cleared to land."),
                            (44, "pilot", "p2", "Cleared to land runway two seven, IFLY six zero five tree.")],
                     expect=[(2, "RUNWAY_CONFLICT", "RED")]),
    "HOLD_AS_CROSS": dict(airport="VIDP", traffic=["AIC2817", "IGO5134"],
                          phases={"AIC2817": "ground", "IGO5134": "ground"},
                          steps=[(0, "tower", "tower", "Air India two eight one seven, runway two niner right, cleared for takeoff."),
                                 (4, "pilot", "p1", "Runway two niner right, cleared for takeoff, Air India two eight one seven."),
                                 (15, "tower", "tower", "IFLY five one tree four, hold short runway two niner right."),
                                 (19, "pilot", "p2", "Crossing runway two niner right, IFLY five one tree four.")],
                          expect=[(3, "READBACK_MISMATCH", "RED"), (3, "RUNWAY_CONFLICT", "RED")]),
    "TWIN_CALLSIGN": dict(airport="VIDP", traffic=["IGO5134", "IGO5124", "AIC2817"],
                          phases={"IGO5134": "air", "IGO5124": "air"},
                          steps=[(0, "tower", "tower", "IFLY five one tree four, runway two eight, cleared to land."),
                                 (4, "pilot", "p3", "Cleared to land runway two eight, IFLY five one two four.")],
                          expect=[(1, "READBACK_MISMATCH", "RED")]),
    "STOP": dict(airport="VAPO", traffic=["AKJ2612", "AIC947"], phases={"AKJ2612": "ground"},
                 steps=[(0, "tower", "tower", "Akasa Air two six one two, runway one zero, cleared for takeoff."),
                        (4, "pilot", "p1", "Runway one zero, cleared for takeoff, Akasa Air two six one two."),
                        (20, "tower", "tower", "Akasa Air two six one two, stop immediately, I say again, stop immediately."),
                        (24, "pilot", "p1", "Stopping, Akasa Air two six one two.")],
                 expect=[]),                 # outcome reported: confirmed, or "STOP not confirmed"
    "BIRDS_MR": dict(airport="VABB", traffic=["AIC657", "BIRDCHASER2"], phases={"AIC657": "ground"},
                     steps=[(0, "tower", "tower", "Air India six five seven, runway two seven, cleared for takeoff."),
                            (4, "pilot", "p1", "Runway two seven, cleared for takeoff, Air India six five seven."),
                            (15, "airside", "veh_mr", "टॉवर, बर्ड चेसर टू, रनवे टू सेवन वर पक्षी आहेत, मी टॅक्सीवे चार्लीजवळ थांबलोय.")],
                     expect=[(2, "BIRDS_ON_ACTIVE_RUNWAY", "RED")]),
    "VEHICLE_HI": dict(airport="VIDP", traffic=["IGO5134", "FOLLOWME3"], phases={"IGO5134": "air"},
                       steps=[(0, "tower", "tower", "IFLY five one tree four, runway two eight, cleared to land."),
                              (4, "pilot", "p2", "Cleared to land runway two eight, IFLY five one tree four."),
                              (30, "airside", "veh_hi", "Tower, Follow Me three, runway two eight cross karna hai, Bravo pe hold kar raha hoon.")],
                       expect=[(2, "VEHICLE_REQUEST_OCCUPIED", "AMBER")]),
    "NORMAL_DEL": dict(airport="VIDP", traffic=["AIC2817", "IGO5134", "AKJ1123"],
                       phases={"AIC2817": "ground", "IGO5134": "air", "AKJ1123": "ground"},
                       steps=[(0, "tower", "tower", "Air India two eight one seven, runway two eight, cleared for takeoff."),
                              (4, "pilot", "p1", "Runway two eight, cleared for takeoff, Air India two eight one seven."),
                              (40, "tower", "tower", "IFLY five one tree four, runway two niner left, cleared to land."),
                              (44, "pilot", "p2", "Cleared to land runway two niner left, IFLY five one tree four."),
                              (70, "tower", "tower", "Akasa Air one one two tree, behind the landing Airbus, line up and wait runway two niner left, behind."),
                              (75, "pilot", "p3", "Behind the landing Airbus, line up and wait runway two niner left, behind, Akasa Air one one two tree."),
                              (150, "pilot", "p2", "Runway vacated, IFLY five one tree four."),
                              (160, "tower", "tower", "Akasa Air one one two tree, runway two niner left, cleared for takeoff."),
                              (164, "pilot", "p3", "Runway two niner left, cleared for takeoff, Akasa Air one one two tree.")],
                       expect=[], no_red=True),
}
