# Rishu demo guide (showcase ke liye)

## Demo se pehle (15 minute)

1. GitHub Releases se `RishuSetup-0.6.0.exe` (ya jo latest ho) download karke install karo.
   "Unknown publisher" aaye to **More info → Run anyway**.
2. Rishu kholo, setup poora karo: naam, bhasha, awaaz, aur **Groq API key**
   (console.groq.com/keys → Create API Key → paste → Check + Save).
3. Laptop ka **internet on** rakho (natural awaaz aur AI ke liye) aur
   **mic/speaker** check kar lo (Windows Settings → Sound).
4. Ek baar practice: mic dabao, "Chrome kholo" bolo.

## Demo flow (5–7 minute)

| # | Aap kya karo / bolo | Kya dikhega |
|---|---|---|
| 1 | App kholo | Animated orb; Rishu khud bolkar namaste karta hai ("Suprabhat Neelesh! Main Rishu hoon…") |
| 2 | Mic dabao: "Namaste Rishu, apna introduction do" | Orb sunte waqt awaaz ke saath hilta hai, phir Rishu bolkar jawab deta hai |
| 3 | "Chrome kholo" | Chrome khulta hai, chat mein ✓ step dikhta hai |
| 4 | "gitm.edu.in kholo" | Website browser mein khulti hai |
| 5 | "Aaj ki AI news search karo" | Web search, Sources card (click karke page khulta hai), bolkar summary |
| 6 | "Mujhe quantum computing simple bhasha mein padhao" | Step-by-step explanation; phir cross-question poochho: "Qubit aur bit mein kya fark hai?" |
| 7 | Bolte waqt beech mein **STOP** (ya Esc) | Rishu turant chup ho jata hai |
| 8 | "Note likho: kal 10 baje HOD ke saath meeting" → "Mere notes dikhao" | Note save aur list |
| 9 | Kisi aur app mein rehte hue **Ctrl+Shift+Space** dabao aur bolo | Rishu kahin se bhi sunta hai |
| 10 | "Gurugram ka mausam batao" | Aaj aur kal ka mausam, bolkar |
| 11 | "1 minute baad mujhe paani peene ka reminder lagao" | 1 minute baad Rishu khud bolkar yaad dilata hai |
| 12 | "Yaad rakho: mera favourite subject DAA hai" → "Nayi baat-cheet" → "Mera favourite subject kya hai?" | Nayi chat mein bhi yaad rehta hai |
| 13 | "WhatsApp pe likho: main 10 minute late hoon" | Permission card → "Haan" → WhatsApp khulta hai, message type hua; Send aap dabao |
| 14 | "Awaaz thodi badhao" | Volume badhta hai |
| 15 | Koi webpage ya code screen par kholo, phir: "Screen par kya hai, samjhao" | Rishu screen dekhkar samjhata hai |
| 15b | Left mein **Kaam** (Activity) tab | Har kaam ka record: risk level, permission |
| 16 | Settings: awaaz Ladka/Ladki badlo, "Sunao" | Awaaz turant badalti hai |
| 16b | (Optional, shaant kamre mein) Settings → Awaaz → **Baat-cheet mode** ON. Mic dabao: "Quantum computing kya hai?" → jawab ke baad bina dabaye: "Ek example do" → "Thank you" | Mic khud khulta hai, lagataar baat-cheet; "Thank you" par Rishu band |
| 16c | Settings → **Rishu ka andaaz** → Personal chuno (awaaz ladki ki ho jaati hai), "Rishu aapko kya bulaye" mein "Neelesh ji" | Rishu pyaar se, apnapan se baat karti hai |
| 18 | "Rishu, main tumhe ek kaam sikhata hoon: gitm.edu.in par admission page kholna" → Rishu ki browser window mein karke dikhao → **Bas, ho gaya** | Banner mein steps dikhte hain; Settings → Seekhe hue kaam mein naya kaam |
| 19 | Lexyta mein meeting ka attendance page Rishu ki browser window mein kholo → "roll 5 aur 12 absent, baaki present" | Permission card → saari pages par attendance lag jaati hai (lock tabhi jab bolo) |
| 20 | Ek Excel file (naam + roll number) Downloads mein rakho → "DAA attendance file mein Aryan ke 8 aur Priya ke 9 marks bharo" | Card mein har row dikhti hai → haan → file bhar jaati hai |
| 21 | "Mera timetable save karo: Monday 9:30 DAA CSE 5 A room 204, …" → "Aaj kaunsi class hai?" | Timetable; class se 10 minute pehle Rishu bolkar yaad dilati hai |
| 22 | "DAA Unit 1 ke notes bana do, Word file mein" / "Sorting par 5 sawaal ka quiz answer key ke saath" | Documents\Rishu mein Word file; "khol do" bolo to khulti hai |
| 23 | Laptop: Settings → **Phone se jodo** → code. Phone: Rishu app → code daalo → **Jodo** → phone par bolo "Aaj kaunsi class hai?" | Laptop wala Rishu jawab deta hai, phone bolkar sunata hai |
| 17 | Settings → Suraksha: PIN set karo, phir bolo **"Rishu lock"** | Rishu turant lock; chat screen se hat jaati hai. PIN (ya Windows Hello / bolkar password) se unlock |

## Agar kuch gadbad ho

- **Mic se jawab nahi aa raha:** Settings mein Groq key check karo; Windows mic
  permission (Settings → Privacy → Microphone → desktop apps allow).
- **Awaaz nahi aa rahi:** top bar ka speaker icon on hai? Internet on hai?
- **"Rishu start nahi ho paaya":** "Dobara try karo" dabao; antivirus ne core ko
  roka ho to Rishu ko allow karo.
- **Mic ki awaaz bilkul nahi pahunch rahi:** Rishu khud bata dega ("Mic se bilkul bhi awaaz nahi aa rahi…");
  Windows Settings → Privacy & security → Microphone → dono switch ON, aur laptop ka mic-mute key check karo.
- **PIN bhool gaye:** Rishu band karo, `%LOCALAPPDATA%\Rishu\lock.json` file delete karo, Rishu dobara kholo
  (lock hat jaayega; Windows account ka access hi asli suraksha hai).
- **Backup:** typing hamesha kaam karti hai; suggestions par click karke bhi demo ho sakta hai.

## Kya bolna hai (pitch)

"Rishu ek Hinglish-first personal AI assistant hai jo laptop par locally chalta
hai. Aap bolo, Rishu samajhta hai, kaam karta hai, padhata hai, aur har zaroori
kaam se pehle permission leta hai. Data aapke computer par encrypted rehta hai.
Aage: Android app, face/fingerprint lock, memory, WhatsApp aur 'teach once'
skills, aur khud ko naye kaam sikhane wala Self-Update Lab."
