"""General Hindi lines (not land-record templates) to check the fine-tuned model did not get worse at ordinary text."""
import random
import sys
from pathlib import Path

import cv2

import synth_lines as gen

SENTENCES = """भारत एक विशाल देश है जिसमें अनेक भाषाएं बोली जाती हैं
आज सुबह से ही आसमान में बादल छाए हुए थे
बच्चों ने विद्यालय में स्वतंत्रता दिवस धूमधाम से मनाया
किसानों को इस वर्ष अच्छी वर्षा की उम्मीद है
सरकार ने नई शिक्षा नीति की घोषणा की
रेलगाड़ी समय से दो घंटे देर से पहुंची
डॉक्टर ने मरीज को आराम करने की सलाह दी
बाजार में सब्जियों के दाम बढ़ गए हैं
पुस्तकालय में हर दिन सैकड़ों पाठक आते हैं
नदी के किनारे एक पुराना मंदिर है
उसने अपनी मां को पत्र लिखा और डाकघर गया
खिलाड़ियों ने कड़ी मेहनत से प्रतियोगिता जीती
गांव में पानी की समस्या गंभीर होती जा रही है
वैज्ञानिकों ने एक नई दवा की खोज की है
हमें पर्यावरण की रक्षा के लिए पेड़ लगाने चाहिए
शहर की सड़कों पर यातायात बहुत अधिक है
परीक्षा का परिणाम अगले सप्ताह घोषित होगा
दादी ने बच्चों को एक रोचक कहानी सुनाई
मौसम विभाग ने तेज बारिश की चेतावनी जारी की
कृपया अपना मोबाइल फोन बंद कर दें
इस पुस्तक का मूल्य दो सौ पचास रुपये है
बैठक में सभी सदस्यों ने अपने विचार रखे
सूर्य पूर्व दिशा में उगता है और पश्चिम में अस्त होता है
अस्पताल में नए उपकरण लगाए गए हैं
उन्होंने कहा कि काम समय पर पूरा होगा
यह सड़क पिछले वर्ष बनाई गई थी
मेले में दूर दूर से लोग आए थे
हिमालय विश्व की सबसे ऊंची पर्वत श्रृंखला है
चुनाव आयोग ने मतदान की तिथि तय कर दी
गर्मी की छुट्टियों में हम नानी के घर गए
विद्यार्थियों को नियमित रूप से अभ्यास करना चाहिए
कंपनी ने अपने कर्मचारियों का वेतन बढ़ाया
रात को आकाश में तारे चमक रहे थे
प्रदूषण के कारण लोगों को सांस लेने में कठिनाई होती है
संगीत मन को शांति देता है
उसने ईमानदारी से अपना कर्तव्य निभाया
नगर निगम ने सफाई अभियान शुरू किया
दुकान सुबह नौ बजे खुलती है
त्योहारों के समय घरों को सजाया जाता है
पुलिस ने मामले की जांच शुरू कर दी है""".splitlines()


def main():
    out, count, seed = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    fonts = [f for f in gen.FONTS if f.stem in sys.argv[4].split(",")]
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    made = 0
    while made < count:
        words = rng.choice(SENTENCES).split()
        if rng.random() < 0.5 and len(words) > 5:  # vary line length like wrapped text
            start = rng.randint(0, len(words) - 4)
            words = words[start:start + rng.randint(4, len(words) - start)]
        text = " ".join(words)
        if not gen.allowed(text):
            continue
        ink = gen.render(text, rng.choice(fonts), rng.randint(28, 56))
        if ink is None:
            continue
        img = gen.degrade(ink, rng)
        name = f"gen_{seed}_{made:04d}"
        cv2.imwrite(str(out / f"{name}.tif"), img)
        (out / f"{name}.gt.txt").write_text(text + "\n", "utf-8")
        (out / f"{name}.box").write_text(gen.box_lines(text, img.shape[1], img.shape[0]), "utf-8")
        made += 1
    print(out, made)


if __name__ == "__main__":
    main()
