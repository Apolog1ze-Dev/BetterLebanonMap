"""Reviewed French and English spellings for words of real Lebanese street names.

The dictionary, the place-name gazetteer and the spellings learned from OSM (lexicon.py) leave a
few hundred words of real OSM street names that would otherwise be spelled letter by letter. Each
was looked up in context (the street name it appears in, and the street's other OSM tags) and
given its usual Lebanese spelling or its translation. Keys are Arabic words or phrases of up to
five words, matched with or without the article "ال"; longer phrases win ("الأمم المتحدة" is
"Nations unies", not "Nations" + "Unies"). French values carry the article or preposition they
take after "Rue" ("de l'Aéroport"), English values are written to precede "Street".
"""

REVIEWED = {
    # Descriptive names, translated
    "المطار": ("de l'Aéroport", "Airport"), "الشام": ("de Damas", "Damascus"),
    "الاستقلال": ("de l'Indépendance", "Independence"), "الحرية": ("de la Liberté", "Liberty"),
    "الأمم المتحدة": ("des Nations unies", "United Nations"), "الأمم": ("des Nations", "Nations"),
    "المتحدة": ("Unies", "United"), "الجيش": ("de l'Armée", "Army"), "الجمارك": ("de la Douane", "Customs"),
    "المحكمة العسكرية": ("du Tribunal militaire", "Military Court"), "المحكمة": ("du Tribunal", "Court"),
    "الطريق العسكرية": ("Route militaire", "Military Road"), "العسكرية": ("militaire", "Military"),
    "المستشفى العسكري": ("de l'Hôpital militaire", "Military Hospital"), "العسكري": ("militaire", "Military"),
    "المهاجرين": ("des Émigrés", "Emigrants"), "الكبوشية": ("des Capucins", "Capuchins"),
    "المصارف": ("des Banques", "Banks"), "المرصد": ("de l'Observatoire", "Observatory"),
    "الشهداء": ("des Martyrs", "Martyrs'"), "الشهيدين": ("des Deux Martyrs", "Two Martyrs"),
    "البرلمان": ("du Parlement", "Parliament"), "البوست": ("de la Poste", "Post Office"),
    "المدارس": ("des Écoles", "Schools"), "الكرنيش": ("de la Corniche", "Corniche"),
    "الأوقاف": ("des Wakfs", "Awqaf"), "الفرسان": ("des Chevaliers", "Knights"),
    "فرسان الهيكل": ("des Templiers", "Knights Templar"), "الدلتا": ("du Delta", "Delta"),
    "الأمن": ("de la Sécurité", "Security"),
    "الأمن للولايات المتحدة الأمريكية": ("de la Sécurité des États-Unis", "US Security"),
    "الواجهة البحرية للمدينة": ("du Front de mer", "City Waterfront"),
    "القصر الرئاسي": ("du Palais présidentiel", "Presidential Palace"), "الرئاسي": ("présidentiel", "Presidential"),
    "المنطقة الخضراء": ("Zone verte", "Green Zone"), "المنطقة": ("Zone", "Zone"), "الخضراء": ("Verte", "Green"),
    "معمل السكر": ("de la Sucrerie", "Sugar Factory"), "100 متر": ("des 100 mètres", "100 Meter"),
    "مدرسة الحقوق": ("de l'École de droit", "Law School"), "الحقوق": ("du Droit", "Law"),
    "الراعي الصالح": ("du Bon Pasteur", "Good Shepherd"), "القلبين الأقدسين": ("des Sacrés-Cœurs", "Sacred Hearts"),
    "القديسين بطرس وبولس": ("des Saints-Pierre-et-Paul", "Saints Peter and Paul"), "القديسين": ("des Saints", "Saints"),
    "الثلاثة أقمار": ("des Trois-Docteurs", "Three Hierarchs"), "نهر الأردن": ("du Jourdain", "Jordan River"),
    "في الصخر": ("dans le Rocher", "in the Rock"),   # كنيسة في الصخر: the church in the rock
    "السوق العتيق": ("du Vieux Souk", "Old Souk"), "العتيق": ("Vieux", "Old"), "السفلي": ("inférieur", "Lower"),
    "الأخوين": ("des Frères", "Brothers"), "الإخوة": ("des Frères", "Brothers"),
    "الأخوين رحباني": ("des Frères Rahbani", "Rahbani Brothers"), "الأخوين فليفل": ("des Frères Flayfel", "Flayfel Brothers"),
    "الإخوة مسابكي": ("des Frères Massabki", "Massabki Brothers"),
    "بيسكينه": ("de la Piscine", "Swimming Pool"), "بيسكين": ("de la Piscine", "Swimming Pool"),
    "كنيسة الإخوة الإنجيليين": ("de l'Église des Frères évangéliques", "Evangelical Brethren Church"),
    "الإنجيليين": ("évangéliques", "Evangelical"), "الكسليك للتسوق": ("commerçante de Kaslik", "Kaslik Shopping"),
    "بنك الاعتماد اللبناني": ("du Crédit libanais", "Credit Libanais Bank"), "بنك": ("de la Banque", "Bank"),
    "جيش لبنان الجنوبي": ("de l'Armée du Liban-Sud", "South Lebanon Army"), "مشروع": ("Machrou", "Mashrou"),
    "فندق": ("de l'Hôtel", "Hotel"), "خاص": ("privée", "Private"), "جامعي": ("universitaire", "University"),
    "قسم": ("Section", "Section"), "نزلت الجيش": ("Nazlet el-Jeich", "Nazlet al-Jaish"),
    "نزلت": ("Nazlet", "Nazlet"), "نزلة": ("Nazlet", "Nazlet"), "فرع": ("Embranchement", "Branch"), "فرعي": ("secondaire", "Secondary"),
    "كونتري كلوب": ("Country Club", "Country Club"), "مارينا ووترفرونت سيتي": ("Marina Waterfront City", "Marina Waterfront City"),
    "اللواء": ("Général", "General"), "العميد": ("Général", "Brigadier"), "المونسينيور": ("Monseigneur", "Monsignor"),
    "الأم": ("Mère", "Mother"), "أبوت": ("Abbé", "Abbot"), "الملك": ("Roi", "King"), "الاستاذ": ("Professeur", "Professor"),
    "الأستاذ": ("Professeur", "Professor"), "البطريك": ("Patriarche", "Patriarch"), "الکقر": ("Docteur", "Doctor"),
    "الصحابي": ("Compagnon", "Companion"), "جمهورية": ("République", "Republic"),
    # Titles, spelled one way everywhere (the learned spellings vary: "Sid", "Es-Saiyed")
    "العلامة": ("Allamé", "Allamah"), "السيد": ("Sayyed", "Sayyed"), "المفتي": ("Mufti", "Mufti"),
    "القاضي": ("Juge", "Judge"), "المختار": ("Moukhtar", "Mukhtar"), "الوزير": ("Ministre", "Minister"),
    "النائب": ("Député", "MP"), "الشاعر": ("Poète", "Poet"), "الأديب": ("Écrivain", "Writer"),
    "المهندس": ("Ingénieur", "Engineer"), "العقيد": ("Colonel", "Colonel"), "المقدم": ("Lieutenant-colonel", "Lieutenant Colonel"),
    "الرائد": ("Commandant", "Major"), "النقيب": ("Capitaine", "Captain"), "الملازم": ("Lieutenant", "Lieutenant"),
    "الرقيب": ("Sergent", "Sergeant"),
    "السيد المسيح": ("du Christ", "Christ"),
    "جمهورية كولومبيا": ("de la République de Colombie", "Republic of Colombia"),
    "جمهورية الدومينيكان": ("de la République dominicaine", "Dominican Republic"),
    "و": ("et", "and"), "دو": ("de", "de"), "دي": ("de", "de"), "أ": ("A", "A"), "إر": ("R", "R"),
    "الأفنسيين": ("des Français", "French"),   # OSM typo for الفرنسيين, tagged "Avenue des Français"
    # Countries and cities
    "أرمينيا": ("d'Arménie", "Armenia"), "أستراليا": ("d'Australie", "Australia"), "أميركا": ("d'Amérique", "America"),
    "الأرجنتين": ("d'Argentine", "Argentina"), "الأروغواي": ("de l'Uruguay", "Uruguay"),
    "الجزائر": ("d'Algérie", "Algeria"), "القاهرة": ("du Caire", "Cairo"), "أثينا": ("d'Athènes", "Athens"),
    "آراس": ("d'Arras", "Arras"), "دو فرانس": ("de France", "France"), "بور سعيد": ("de Port-Saïd", "Port Said"),
    "صيدا": ("Saïda", "Saida"),
    "بيت لحم": ("de Bethléem", "Bethlehem"), "صيدنايا": ("Saydnaya", "Saidnaya"),
    "سيدة صيدنايا": ("Notre-Dame de Saydnaya", "Our Lady of Saidnaya"), "طرابس": ("Tripoli", "Tripoli"),
    "شيلي": ("du Chili", "Chile"), "تشيلي": ("du Chili", "Chile"), "المكسيك": ("du Mexique", "Mexico"),
    "قلعة الشقيف": ("du Château de Beaufort", "Beaufort Castle"),
    "بيت المهندس": ("de la Maison de l'Ingénieur", "Engineer's House"),
    "مكتبة أنطوان": ("de la Librairie Antoine", "Librairie Antoine"),   # the bookshop chain
    "الخرائب": ("Kharayeb", "Kharayeb"), "مدينة الصناعية": ("Cité industrielle", "Industrial City"),
    "المدينة الصناعية": ("de la Cité industrielle", "Industrial City"),
    # Names whose OSM tags turned out to belong to another street (see network.way_names)
    "الوحدة الوطنية": ("de l'Unité nationale", "National Unity"), "عمرو بن العاص": ("Amr Ibn el-Aas", "Amr ibn al-As"),
    "ج ب كرم": ("J. P. Karam", "J. P. Karam"), "شاطئ البحر": ("du Bord de mer", "Seaside"),
    "المغتربين": ("des Émigrés", "Emigrants"), "المسيحيين": ("des Chrétiens", "Christians"),
    "الأمريكان": ("des Américains", "American"), "الأميركان": ("des Américains", "American"),
    "السفارة الكويتية": ("de l'Ambassade du Koweït", "Kuwaiti Embassy"), "الحياكين": ("des Tisserands", "Weavers"),
    "جسر المشاة": ("Passerelle", "Footbridge"), "قداسة البابا": ("de Sa Sainteté le Pape", "His Holiness the Pope"),
    "نفق سليم سلام": ("Tunnel Salim Salam", "Salim Salam Tunnel"), "نفق": ("Tunnel", "Tunnel"),
    # Marian titles as churches are named ("كنيسة سيدة البحر": "Our Lady of the Sea Church")
    "سيدة البحر": ("Notre-Dame de la Mer", "Our Lady of the Sea"), "سيدة لبنان": ("Notre-Dame du Liban", "Our Lady of Lebanon"),
    "سيدة البشارة": ("Notre-Dame de l'Annonciation", "Our Lady of the Annunciation"),
    "سيدة النجاة": ("Notre-Dame de la Délivrance", "Our Lady of Deliverance"),
    "سيدة السلام": ("Notre-Dame de la Paix", "Our Lady of Peace"), "سيدة الجمهور": ("Notre-Dame de Jamhour", "Our Lady of Jamhour"),
    # Schools known by their own names ("Collège Notre-Dame de Jamhour", not "Our Lady of Jamhour School")
    "مدرسة سيدة الجمهور": ("Collège Notre-Dame de Jamhour", "Notre-Dame de Jamhour College"),
    "الرهبان الأنطونية": ("des Pères Antonins", "Antonine Fathers"),
    "العاملية": ("Aamiliyé", "Aamiliyeh"),
    "الأرز": ("des Cèdres", "Cedars"),   # The Cedars above Bcharré, as roads name it ("طريق الأرز - بعلبك")
    "خديجة الكبرى": ("Khadigé el-Koubra", "Khadija al-Kubra"),   # an epithet, not "Khadigé Grande"
    "النبي شيث": ("Nabi Chit", "Nabi Chit"),                     # the town, as the commune list spells it (نبي شيت)
    "مرعي": ("Merhi", "Merhi"),                                   # the first and family name ("Merhi Abou Merhi"), not "Maraï"
    "سيدة المعونات": ("Notre-Dame du Secours", "Our Lady of Help"), "سيدة المعونة": ("Notre-Dame du Secours", "Our Lady of Help"),
    "سيدة النياح": ("Notre-Dame de la Dormition", "Our Lady of the Dormition"),
    "سيدة الانتقال": ("Notre-Dame de l'Assomption", "Our Lady of the Assumption"),
    "سيدة لورد": ("Notre-Dame de Lourdes", "Our Lady of Lourdes"), "سيدة الملائكة": ("Notre-Dame des Anges", "Our Lady of the Angels"),
    "سيدة النورية": ("Notre-Dame de Nourieh", "Our Lady of Nourieh"), "سيدة الرسل": ("Notre-Dame des Apôtres", "Our Lady of the Apostles"),
    "سيدة المنطرة": ("Notre-Dame de Mantara", "Our Lady of Mantara"), "سيدة البير": ("Notre-Dame du Puits", "Our Lady of the Well"),
    "سيدة الفرح": ("Notre-Dame de la Joie", "Our Lady of Joy"), "سيدة الوردية": ("Notre-Dame du Rosaire", "Our Lady of the Rosary"),
    "سيدة الخلاص": ("Notre-Dame du Salut", "Our Lady of Salvation"),
    # Places
    "الحجير": ("el-Houjeir", "al-Hujeir"), "كفرايا": ("Kefraya", "Kefraya"), "قاب إلياس": ("Qab Elias", "Qab Elias"),
    "قاب": ("Qab", "Qab"), "العبودية الدبوسية": ("Aabboudiyé - Dabboussiyé", "Aabboudiyeh - Dabboussiyeh"),
    "الدبوسية": ("Dabboussiyé", "Dabboussiyeh"), "الرفاعية": ("er-Rifaiyé", "ar-Rifaiyeh"), "بسايا": ("Bsaya", "Bsaya"),
    "اوديس": ("Odaïssé", "Odaisseh"), "تعلبيا": ("Taalabaya", "Taalabaya"), "كفرحاتا": ("Kfarhata", "Kfarhata"),
    "قنافر": ("Qanafar", "Qanafar"), "خلة": ("Khallet", "Khallet"), "خندق الغميق": ("Khandak el-Ghamik", "Khandaq al-Ghamiq"),
    "الغميق": ("el-Ghamik", "al-Ghamiq"), "العازرية": ("Azarieh", "Azarieh"), "عين ورقة": ("Aïn Warqa", "Ain Warqa"),
    "نبع اللبن": ("Nabaa el-Laban", "Nabaa al-Laban"), "نبعة المطران": ("Nabaa el-Matrane", "Nabaa al-Matran"),
    "نبعة": ("Nabaa", "Nabaa"), "فرن": ("Forn", "Forn"), "الغلغول": ("Ghalghoul", "Ghalghoul"),
    "ساقية الجنزير": ("Sakiet el-Janzir", "Saqiyat al-Janzir"), "الزغل": ("ez-Zaghl", "az-Zaghl"),
    "الحرش": ("el-Horch", "al-Horsh"), "الحرافشة": ("el-Harafché", "al-Harafsheh"), "فوقا": ("Faouqa", "Fawqa"),
    "السهل": ("es-Sahl", "as-Sahl"), "السكة": ("es-Sekké", "as-Sikkeh"), "القلع": ("el-Qalaa", "al-Qalaa"),
    "المستوية": ("el-Moustawiyé", "al-Mustawiyeh"), "الغزالية": ("el-Ghazaliyé", "al-Ghazaliyeh"),
    "الزاقوق": ("ez-Zakkouk", "az-Zakkouk"), "البدركان": ("el-Badrakan", "al-Badrakan"), "شكارة": ("Chkara", "Chkara"),
    "سفيلا": ("Sfayla", "Sfayla"),
    "الجامعة اللبنانية الأمريكية": ("Université libano-américaine", "Lebanese American University"),
    "الجامعة اللبنانية الأميركية": ("Université libano-américaine", "Lebanese American University"),
    "مدرسة الحكمة": ("École de la Sagesse", "La Sagesse School"), "جامعة الحكمة": ("Université La Sagesse", "La Sagesse University"),
    "الحكمة": ("de la Sagesse", "Sagesse"), "المحافظ": ("el-Mohafez", "al-Mohafez"), "جماران": ("Jamaran", "Jamaran"), "الغبرا": ("el-Ghabra", "al-Ghabra"),
    "النمرة": ("en-Nimra", "an-Nimra"), "القرش": ("el-Qirch", "al-Qirsh"), "الصراصير": ("es-Sarassir", "as-Sarasir"),
    "البربيطة": ("el-Barbita", "al-Barbita"), "الخضرة": ("el-Khodra", "al-Khodra"), "رعيان": ("Raayane", "Raayan"),
    "فخيته": ("Fekhayteh", "Fekhayteh"), "المواساة": ("el-Mouassat", "al-Mouassat"), "الثريا": ("Thouraya", "Thuraya"),
    "صباغة": ("Sabbagha", "Sabbagha"), "القطان": ("el-Qattan", "al-Qattan"), "حابيس": ("Habis", "Habis"),
    "غاريني": ("Garine", "Garine"), "كاريتاس": ("Caritas", "Caritas"), "بون جوس": ("Bonjus", "Bonjus"),
    "كرواسون الطيب": ("Croissant et-Tayeb", "Croissant at-Tayeb"), "الأليانس": ("de l'Alliance", "Alliance"),
    "المارسيياز": ("de la Marseillaise", "Marseillaise"), "البر والإحسان": ("el-Birr wal-Ihsane", "al-Birr wal-Ihsan"),
    "ىحال": ("Rahal", "Rahal"),   # OSM typo for رحال, tagged "Rue Karm Rahal"
    # Compound first names
    "عبد الله": ("Abdallah", "Abdallah"), "عبد الرحمن": ("Abdel Rahman", "Abdel Rahman"),
    "عبد السلام": ("Abdel Salam", "Abdel Salam"), "عبد المنعم": ("Abdel Moneim", "Abdel Moneim"),
    "عبد الغني": ("Abdel Ghani", "Abdel Ghani"), "عبد الباسط": ("Abdel Basset", "Abdel Basset"),
    "عبد العزيز": ("Abdel Aziz", "Abdel Aziz"), "عبد الكريم": ("Abdel Karim", "Abdel Karim"),
    "عبد الحميد": ("Abdel Hamid", "Abdel Hamid"), "عبد القادر": ("Abdel Kader", "Abdel Kader"),
    "عبد الرحيم": ("Abdel Rahim", "Abdel Rahim"), "عبد الناصر": ("Abdel Nasser", "Abdel Nasser"),
    "عبد اللطيف": ("Abdel Latif", "Abdel Latif"), "عبد الوهاب": ("Abdel Wahab", "Abdel Wahab"),
    "عبد المجيد": ("Abdel Majid", "Abdel Majid"), "عبد الحسين": ("Abdel Hussein", "Abdel Hussein"),
    "عبد الحليم": ("Abdel Halim", "Abdel Halim"), "عبد الرزاق": ("Abdel Razzak", "Abdel Razzaq"),
    "عبد العدي": ("Abdel Adi", "Abdel Adi"), "عبد النور": ("Abdel Nour", "Abdel Nour"), "عبدالنور": ("Abdel Nour", "Abdel Nour"),
    "عبد الأمير": ("Abdel Amir", "Abdel Amir"), "عبد الفتاح": ("Abdel Fattah", "Abdel Fattah"),
    "محي الدين": ("Mohieddine", "Mohieddine"), "محيي الدين": ("Mohieddine", "Mohieddine"),
    "عز الدين": ("Ezzeddine", "Ezzeddine"), "عزالدين": ("Ezzeddine", "Ezzeddine"), "نور الدين": ("Noureddine", "Noureddine"),
    "بهاء الدين": ("Bahaeddine", "Bahaeddine"), "صلاح الدين": ("Salaheddine", "Salaheddine"),
    "صلاح الدين الأيوبي": ("Salaheddine el-Ayoubi", "Saladin"), "الأيوبي": ("el-Ayoubi", "al-Ayyubi"),
    "خير الدين": ("Kheireddine", "Kheireddine"), "خير": ("Kheir", "Kheir"), "فخر الدين": ("Fakhreddine", "Fakhreddine"),
    "فخر": ("Fakhr", "Fakhr"), "علم الدين": ("Alameddine", "Alameddine"), "علم": ("Alam", "Alam"),
    "ناصر الدين": ("Nasreddine", "Nasreddine"), "ناصر": ("Nasser", "Nasser"), "شرف الدين": ("Charafeddine", "Sharafeddine"),
    "زين الدين": ("Zeineddine", "Zeineddine"), "شمس الدين": ("Chamseddine", "Shamseddine"),
    "بدر الدين": ("Badreddine", "Badreddine"), "جمال الدين": ("Jamaleddine", "Jamaleddine"),
    "تقي الدين": ("Takieddine", "Takieddine"), "سيف الدين": ("Seifeddine", "Seifeddine"),
    "كمال الدين": ("Kamaleddine", "Kamaleddine"), "علاء الدين": ("Alaeddine", "Alaeddine"),
    "عطاء الله": ("Atallah", "Atallah"), "عطاء": ("Ata", "Ata"), "فتح الله": ("Fathallah", "Fathallah"), "فتح": ("Fath", "Fath"),
    "نصر الله": ("Nasrallah", "Nasrallah"), "نصرالله": ("Nasrallah", "Nasrallah"), "فضل الله": ("Fadlallah", "Fadlallah"),
    "جاد الله": ("Jadallah", "Jadallah"), "خير الله": ("Khairallah", "Khairallah"), "رزق الله": ("Rizkallah", "Rizkallah"),
    "عثمان بن عفان": ("Othman ben Affane", "Uthman ibn Affan"), "عثمان": ("Osman", "Othman"),
    "إسحاق بن حنين": ("Ishaq ben Hunayn", "Ishaq ibn Hunayn"), "إسحاق": ("Ishac", "Ishaq"),
    "الصحابي شرحبيل بن حسنة": ("Compagnon Chourahbil ben Hassana", "Companion Shurahbil ibn Hasana"),
    "الملك فهد بن عبد العزيز": ("du Roi Fahd ben Abdelaziz", "King Fahd bin Abdulaziz"),
    "الأخطل الصغير": ("Akhtal es-Saghir", "Akhtal al-Saghir"), "الصغير": ("es-Saghir", "as-Saghir"),
    # First names
    "هادي": ("Hadi", "Hadi"), "ألفرد": ("Alfred", "Alfred"), "نزيه": ("Nazih", "Nazih"), "ألكسندر": ("Alexandre", "Alexander"),
    "أليس": ("Alice", "Alice"), "مايكل": ("Michael", "Michael"), "بنوا": ("Benoît", "Benoit"), "أوغست": ("Auguste", "Auguste"),
    "أليكسندروس": ("Alexandros", "Alexandros"), "قسطنطين": ("Constantin", "Constantine"), "ألكسي": ("Alexis", "Alexis"),
    "جوزف": ("Joseph", "Joseph"), "لبيب": ("Labib", "Labib"), "سعدي": ("Saadi", "Saadi"), "أكرم": ("Akram", "Akram"),
    "حسيب": ("Hassib", "Hassib"), "بازيل": ("Basile", "Basil"), "غسان": ("Ghassan", "Ghassan"), "فردوس": ("Ferdous", "Firdous"),
    "غريغوريوس": ("Grégorios", "Gregorios"), "وارطان": ("Vartan", "Vartan"), "عشير": ("Achir", "Ashir"),
    "نعمة يافت": ("Néemé Yafet", "Neemeh Yafet"), "نعمة": ("Néemé", "Neemeh"), "يافت": ("Yafet", "Yafet"),
    # Family names
    "نصر": ("Nasr", "Nasr"), "بزري": ("Bizri", "Bizri"), "عريس": ("Ariss", "Ariss"), "الهراوي": ("Hraoui", "Hrawi"),
    "غانم": ("Ghanem", "Ghanem"), "المشنوق": ("Machnouk", "Machnouk"), "صايغ": ("Sayegh", "Sayegh"),
    "الشافعي": ("Chafeï", "Shafii"), "غزال": ("Ghazal", "Ghazal"), "قاوقجي": ("Kaoukji", "Kaoukji"),
    "حريم": ("Harim", "Harim"), "كنفاني": ("Kanafani", "Kanafani"), "مروه": ("Mroueh", "Mroueh"),
    "جنون": ("Jannoun", "Jannoun"), "كسبار": ("Kasbar", "Kasbar"), "الغلايني": ("Ghalayini", "Ghalayini"),
    "الجارودي": ("Jaroudi", "Jaroudi"), "زغيب": ("Zgheib", "Zgheib"), "الشاغوري": ("Chaghouri", "Shaghouri"),
    "الأغر": ("el-Agharr", "al-Agharr"), "المكاوي": ("el-Makkaoui", "al-Makkawi"), "عراجي": ("Araji", "Araji"),
    "النوام": ("Nawwam", "Nawwam"), "الغزيري": ("Ghaziri", "Ghaziri"), "وهبه": ("Wehbé", "Wehbe"),
    "كاترو": ("Catroux", "Catroux"), "الدويي": ("Douaihy", "Douaihy"), "الغزاوي": ("Ghazzaoui", "Ghazzawi"),
    "التنوخي": ("Tannoukhi", "Tanukhi"), "فريج": ("Freige", "Freige"), "تللو": ("Tellou", "Tellou"),
    "الكستي": ("Kasti", "Kasti"), "طرازي": ("Tarrazi", "Tarrazi"), "الدايه": ("ed-Dayé", "ad-Daya"),
    "عدرة": ("Adra", "Adra"), "الحويك": ("Hoayek", "Howayek"), "مكوك": ("Makkouk", "Makkouk"),
    "الفارابي": ("Farabi", "Farabi"), "الخياط": ("Khayat", "Khayat"), "الزعني": ("Zaani", "Zaani"),
    "عبلا": ("Abla", "Abla"), "حمية": ("Hamiyé", "Hamieh"), "سليماني": ("Soleimani", "Soleimani"),
    "داغر": ("Dagher", "Dagher"), "بسترس": ("Bustros", "Bustros"), "حجي": ("Hajji", "Hajji"),
    "الجعيص": ("Jeaïss", "Jeaiss"), "بعاصيري": ("Baasiri", "Baasiri"), "طيع": ("Tayeh", "Tayeh"),
    "الغزالي": ("Ghazali", "Ghazali"), "أغا": ("Agha", "Agha"), "نعيمة": ("Naimy", "Naimy"),
    "حجازي": ("Hijazi", "Hijazi"), "عزام": ("Azzam", "Azzam"), "خشان": ("Khachan", "Khashan"),
    "بارود": ("Baroud", "Baroud"), "الحمار": ("el-Hammar", "al-Hammar"), "الربيع": ("er-Rabih", "ar-Rabi"),
    "صبرا": ("Sabra", "Sabra"),
    # Foreign names written in Arabic
    "ديغول": ("de Gaulle", "de Gaulle"), "فيكتور هوغو": ("Victor Hugo", "Victor Hugo"), "هوغو": ("Hugo", "Hugo"),
    "ميكل أنج": ("Michel-Ange", "Michelangelo"), "مايكل دبغي": ("Michael DeBakey", "Michael DeBakey"),
    "دبغي": ("DeBakey", "DeBakey"), "المهتما غاندي": ("Mahatma Gandhi", "Mahatma Gandhi"), "غاندي": ("Gandhi", "Gandhi"),
    "بايارد دوج": ("Bayard Dodge", "Bayard Dodge"), "رابندرانات طاغور": ("Rabindranath Tagore", "Rabindranath Tagore"),
    "طاغور": ("Tagore", "Tagore"), "ليوناردو دافنشي": ("Léonard de Vinci", "Leonardo da Vinci"),
    "فانديك": ("Van Dyck", "Van Dyck"), "غورو": ("Gouraud", "Gouraud"), "ويغان": ("Weygand", "Weygand"),
}

# Saints by their Western names after القديس / القديسة ("كنيسة القديس يوسف" -> "Église Saint-Joseph" /
# "Saint Joseph Church", not "Saint Youssef"); "مار يوسف" stays "Mar Youssef", as Lebanon says it.
SAINTS = {"يوسف": ("Joseph", "Joseph"), "جرجس": ("Georges", "George"), "جاورجيوس": ("Georges", "George"),
          "الياس": ("Élie", "Elias"), "إلياس": ("Élie", "Elias"), "ميخائيل": ("Michel", "Michael"),
          "مخايل": ("Michel", "Michael"), "بطرس": ("Pierre", "Peter"), "بولس": ("Paul", "Paul"), "يوحنا": ("Jean", "John"),
          "انطونيوس": ("Antoine", "Anthony"), "أنطونيوس": ("Antoine", "Anthony"), "نقولا": ("Nicolas", "Nicholas"),
          "شربل": ("Charbel", "Charbel"), "مارون": ("Maron", "Maron"), "سمعان": ("Simon", "Simon"),
          "اسطفان": ("Étienne", "Stephen"), "سركيس": ("Serge", "Sergius"), "فرنسيس": ("François", "Francis"),
          "متى": ("Matthieu", "Matthew"), "لوقا": ("Luc", "Luke"), "مرقس": ("Marc", "Mark"), "توما": ("Thomas", "Thomas"),
          "اندراوس": ("André", "Andrew"), "يعقوب": ("Jacques", "James"), "دانيال": ("Daniel", "Daniel"),
          "تقلا": ("Thècle", "Thecla"), "ريتا": ("Rita", "Rita"), "تريزا": ("Thérèse", "Theresa"),
          "تيريزا": ("Thérèse", "Theresa"), "مارينا": ("Marine", "Marina"), "رفقا": ("Rafqa", "Rafqa"),
          "بربارة": ("Barbe", "Barbara"), "حنة": ("Anne", "Anne"), "كاترينا": ("Catherine", "Catherine"),
          "مريم": ("Marie", "Mary")}
FEMALE_SAINTS = {"تقلا", "ريتا", "تريزا", "تيريزا", "مارينا", "رفقا", "بربارة", "حنة", "كاترينا", "مريم"}
for _ar, (_fr, _en) in SAINTS.items():
    _female = _ar in FEMALE_SAINTS
    REVIEWED.setdefault(f"{'القديسة' if _female else 'القديس'} {_ar}", (f"{'Sainte' if _female else 'Saint'}-{_fr}", f"Saint {_en}"))
# Saints and Marian titles are fixed translations, like the dictionary's words (a landmark may use them).
SACRED = {k for k in REVIEWED if k.startswith(("سيدة ", "القديس ", "القديسة ", "القديسين ", "الرهبان ", "مدرسة سيدة "))}

# Latin words and phrases of real street names tagged only in Latin script -> Arabic. Keys are
# matched without case or accents; acronyms ("WBCC", "F.R.A.") and initials stay in Latin.
REVIEWED_LATIN = {
    # Places
    "kfarzabad": "كفرزبد", "bejje": "بجة", "oubeidet": "عبيدات", "shweyr": "الشوير", "dhor": "ضهور",
    "mrouje": "المروج", "aitanit": "عيتنيت", "qoubbeyaa": "القبيات", "jeddeyil": "جدايل", "mraijet": "مريجات",
    "kfar debiane": "كفردبيان", "kfer helda": "كفرحلدا", "ain ed daiaa": "عين الضيعة", "amchit": "عمشيت",
    "hebbaq": "حباق", "machgarah": "مشغرة", "mghairiye": "المغيرية", "zrarieh": "الزرارية", "kafifane": "كفيفان",
    "vahchouch": "يحشوش", "sed": "سد", "besta": "بسطة", "marj el zuhoor": "مرج الزهور", "zuhoor": "الزهور",
    "karmel zettoun": "كرم الزيتون", "haret ei sett": "حارة الست", "sett": "الست", "ghsain": "الغصين",
    "mitain": "المتين", "haoch": "حوش", "haouch": "حوش", "oumara": "الأمراء", "jourit": "جوريت",
    "beit el boumeh": "بيت البومة", "boumeh": "البومة", "ghomeq": "الغميق", "souk el tawileh": "سوق الطويلة",
    "tawileh": "الطويلة", "souk el arwam": "سوق الأروام", "arwam": "الأروام", "souq busros": "سوق بسترس",
    "busros": "بسترس", "souk ayyas": "سوق إياس", "ayyas": "إياس", "sahet": "ساحة", "kouds": "القدس",
    "ruines omeyyades d'anjar": "آثار عنجر الأموية", "omeyyade": "الأمويين", "omeyyades": "الأمويين",
    "sentier de montagne du liban": "درب جبل لبنان", "mont la salle": "مون لاسال",
    # Words
    "chemin": "درب", "montee": "طلعة", "sortie": "مخرج", "entree": "مدخل", "cour": "باحة", "centrale": "المركزية",
    "maternelle": "الحضانة", "residential": "السكني", "residence": "إقامة", "piscine": "المسبح",
    "seaside": "شاطئ البحر", "liberateurs": "المحررين", "advocat": "المحامي", "avocat": "المحامي",
    "poete": "الشاعر", "commandant": "الرائد", "colonel": "العقيد", "catholicos": "الكاثوليكوس",
    "mere": "الأم", "soeur": "الأخت", "sœr": "الأخت", "sœur": "الأخت", "sainte famille": "العائلة المقدسة",
    "famille": "العائلة", "jardins": "الحدائق", "jasmins": "الياسمين", "jamins": "الياسمين", "nakhel": "النخل",
    "snoubar": "الصنوبر", "tilal": "التلال", "karme": "كرمة", "fontaine du bonheur": "نافورة السعادة",
    "fontaine": "نافورة", "bonheur": "السعادة", "pavillons": "الأجنحة", "garage": "الكاراج", "farm": "المزرعة",
    "maisons": "المنازل", "privee": "الخاصة", "perses": "الفرس", "arc": "قوس", "casino": "الكازينو",
    "round about": "مستديرة", "round-about": "مستديرة", "approach road": "طريق المدخل", "united nations": "الأمم المتحدة",
    "maktabet": "مكتبة", "lebanon mountain trail": "درب جبل لبنان", "section": "القسم", "deutsche schule": "المدرسة الألمانية", "saydet al najat": "سيدة النجاة",
    "saydet": "سيدة", "najat": "النجاة", "saydeh": "السيدة", "shari": "شارع", "city": "سيتي", "chalet suisse": "شاليه سويس",
    # People
    "raphael": "رافائيل", "chakhtoura": "شختورة", "hanne": "حنة", "chaoul": "شاوول", "farroukh": "فروخ",
    "lemgo": "ليمغو", "hortance": "هورتانس", "rassi": "الراسي", "bakhost": "باخوس", "adiba": "أديبة",
    "ishac": "إسحاق", "zayat": "الزيات", "dagher": "داغر", "zareh": "زاره", "naregatsi": "ناريكاتسي",
    "sassoun": "ساسون", "der kaloustian": "در كالوستيان", "kaloustian": "كالوستيان", "sannin": "صنين",
    "komidas": "كوميداس", "jibran": "جبران", "zeitlian": "زيتليان", "anteryasian": "أنترياسيان", "dikran": "ديكران",
    "ghophrael": "غفرائيل", "choueiri": "شويري", "abdel-ghani el-mikati": "عبد الغني الميقاتي", "ghani": "الغني",
    "dabbous": "دبوس", "ibn khalboun": "ابن خلدون", "osman": "عثمان", "souleiman": "سليمان", "stavro": "ستافرو",
    "jabra": "جبرا", "rizkallah": "رزق الله", "hasbani": "حاصباني", "hatoum": "حاطوم", "aawar": "العور",
    "ouayda": "عويدا", "sobhi": "صبحي", "antar": "عنتر", "watfa": "وطفة", "saliby": "صليبي", "feghali": "فغالي",
    "pepe": "بيبي", "de gaulle": "ديغول", "gaulle": "ديغول", "elphajj": "الحاج", "karageozian": "كاراغوزيان",
    "galien": "جالينوس", "venessa": "فانيسا", "aghajanian": "أغاجانيان", "chiraz": "شيراز", "mashdots": "ماشدوتس",
    "skaf": "سكاف", "nkoula": "نقولا", "radwan": "رضوان", "dakkach": "دكاش", "rajaa": "رجاء", "norair": "نوراير",
    "mike": "مايك", "rabih": "ربيع", "namous": "الناموس", "baalbaki": "بعلبكي", "sadr": "الصدر",
    "abel alhussein": "عبد الحسين", "alhussein": "الحسين", "mousaui": "الموسوي", "gouraud": "غورو",
    "tawil": "الطويل", "chahrouri": "شحروري", "moawad": "معوض", "maurice": "موريس", "fayed": "فايد",
    "philippides": "فيليبيدس", "michaca": "مشاقة", "kouatly": "القوتلي", "bellot": "بيلو", "yahaya": "يحيى",
    "teresa": "تيريزا", "yaakoub": "يعقوب", "ghattas": "غطاس", "mouaiyad": "مؤيد", "almekawe": "المكاوي",
    "val verde": "فال فيردي", "alice": "أليس", "demirjian": "دميرجيان", "yervant": "يرفانت", "emilie": "إميلي",
    "melhem": "ملحم", "amoun": "عمون", "alias": "إلياس", "hubert": "هوبير", "noel": "نويل", "nancy": "نانسي",
    "chedad": "شداد", "omran": "عمران", "araji": "عراجي", "tabbouni": "طبوني", "houssien": "حسين",
    "harkat": "حركات", "condor": "كوندور", "serenity": "سيرينيتي", "vitalium": "فيتاليوم", "ceratonia": "سيراتونيا",
    "skylark": "سكايلارك", "lilium": "ليليوم", "venue": "قاعة", "ghozaiyel": "الغزيل", "misk": "مسك",
    "atcl": "ATCL", "adex": "ADEX", "vallee ferzol": "وادي فرزل",
    # Settled from sources: the cadaster or locality the street is in (OCHA COD-AB; the CAS list of
    # Lebanese localities, wiki.openstreetmap.org/wiki/LebanonPlaceNames) or the person it honours.
    "haoch el zaraane": "حوش الزراعنة", "zaraane": "الزراعنة",   # CAS 51113 Zahleh Haouch ez-Zaraaneh
    "bakhistay": "بخشتيه", "bkhichtay": "بخشتيه",              # CAS 24321 Bkhichtay (Aley)
    "baaqrif": "بعقريف",                                       # CAS 22423 Baaqrif (Matn)
    "jaayel": "جعايل",                                         # CAS 23455 Jaayel Kfar Niss (Chouf)
    "aibri": "عبري", "yahchouch aibri": "يحشوش - عبري",         # CAS 25479 Aabri (Keserwan, like Yahchouch)
    "assayran": "عسيران",   # Father Afif Osseiran (1919-1988), founder of a Home of Divine Providence in Fanar
    # Whole names
    "rue principale": "الشارع الرئيسي", "1st main street": "الشارع الرئيسي الأول",
    "2nd main street": "الشارع الرئيسي الثاني", "tj village approach road": "طريق مدخل قرية TJ",
    "entree/sortie 2": "مدخل/مخرج 2", "route comite/logement": "طريق اللجنة/السكن",
}


# Words of Latin-only OSM street names whose Arabic original was not found in OSM, the CAS list of
# localities or web sources: phonetic transcriptions of OSM's spelling, checked by hand. Streets
# using them are marked "transcribed" (in the data and on the street card), not presented as
# verified Arabic names.
TRANSCRIBED_LATIN = {
    "sirbeih": "سربيه", "moabbi": "معبي", "radouf": "رادوف", "kouks": "كوكس", "kfarhaseed": "كفرحسيد",
    "biaa": "بيعة", "wadi heb": "وادي هب", "heb": "هب", "jean de cruet": "جان دو كرويه", "cruet": "كرويه",
    "tarik e farrin": "طريق إفرين", "garakia": "غاراكيا", "abourousse": "أبو روس", "sayyour": "سيور",
    "nyareb": "نيارب",
}
