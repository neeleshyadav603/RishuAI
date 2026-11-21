# Neelesh ke liye: aapse kya chahiye

Yeh file sirf un cheezon ki list hai jo **sirf aap** kar sakte ho. Baaki kaam
Rishu ki build apne aap chalti rehti hai. Abhi koi bhi cheez kaam ko rok nahi
rahi hai: neeche wala kaam jab time mile tab kar dena.

## 0. Lexyta ke 4 page dobara bhejo (marks wala kaam inke bina adhoora rahega)

Aapne 10 page bheje the, unme se 6 mil gaye (sign-in, home, courses, course modules,
meetings, attendance). Baaki 4 file **khaali (0 byte)** aayi, shayad upload beech mein
ruk gaya. 21 Nov ko dobara bheje gaye page bhi wahi 4 khaali file the. Tab tak
**teach mode** se kaam chal jaayega: Rishu ki browser window mein ek baar marks
chadhakar dikha do aur "Bas, ho gaya" bolo. Ye page Chrome mein kholkar Ctrl+S → "Webpage, Single File" se save karke
chat mein dobara bhejo:

1. Class ka **Assignments** tab (assignments ki list)
2. Kisi ek assignment ka **Gradebook** (jahan marks bharte ho)
3. **Sessional** marks bharne wala page (agar alag hai)
4. Kisi ek bachche ka **submission** (jahan uski Word file dikhti hai)

Password wali screen mat bhejna.

## 1. Android APK ke liye signing key (5 minute, ek hi baar)

**Kyun:** Abhi APK "debug key" se sign hoti hai, jo har build par badal jaati
hai. Is wajah se phone par naya version install karne se pehle purana Rishu
uninstall karna padta hai. Apni permanent key lagane ke baad update seedha
purane ke upar install hoga. Yeh key sirf aapke paas honi chahiye, isliye main
ise khud nahi bana sakta.

**Kaise (Windows laptop par):**

1. Project folder mein PowerShell kholo (folder mein Shift + Right click →
   "Open PowerShell window here"), aur yeh command chalao:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\make_android_keystore.ps1
   ```

2. Agar script bole ki Java chahiye, to yeh chalao aur phir step 1 dobara karo:

   ```powershell
   winget install EclipseAdoptium.Temurin.17.JDK
   ```

3. Script 4 baar browser mein GitHub ka "New secret" page kholegi. Har baar:
   - **Name** mein woh naam type karo jo PowerShell mein dikh raha hai
     (jaise `ANDROID_KEYSTORE_BASE64`),
   - **Secret** box mein Ctrl+V karo (value pehle se copy hoti hai),
   - **Add secret** dabao, phir PowerShell mein Enter dabao.

4. Script key ko `C:\Users\<aapka naam>\rishu-signing` folder mein rakhti hai.
   **Is folder ka ek private backup rakh lo** (pen drive ya apni private Google
   Drive). Ise kisi ko mat bhejna aur project folder mein mat daalna. Yeh key
   kho gayi to purane installs par update nahi ho payega.

Iske baad agli build apne aap aapki key se sign hogi. Mujhe batane ki zaroorat
nahi hai: build khud check kar leti hai ki secret maujood hai ya nahi.

---

### Technical details (English)

- Secrets read by `.github/workflows/build.yml`: `ANDROID_KEYSTORE_BASE64`,
  `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
- Without them the release APK is signed with the runner's debug key (a new one
  on every run), so in-place updates on a phone fail with a signature mismatch.
- The keystore must never be committed: the repository is public.
