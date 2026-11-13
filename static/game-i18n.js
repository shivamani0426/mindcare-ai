/* Patient game text localization.
   Text nodes only: never change dataset answer keys or patient-entered family names. */
(() => {
  'use strict';
  const root = document.getElementById('game-root');
  if (!root) return;
  const lang = (document.documentElement.lang || 'en').slice(0,2);
  const dict = {
    hi: {
      'Gentle':'आसान','Growing':'बढ़ता','Challenge':'चुनौती','level':'स्तर',
      'Take your time':'आराम से खेलें','Find two cards with matching pictures.':'दो एक जैसे चित्र खोजें।',
      'Take a moment to remember the words. Press ready when you feel comfortable.':'शब्द याद करें। तैयार होने पर आगे बढ़ें।',
      'Look at the number sequence. Press ready when you want to try.':'अंकों का क्रम देखें। तैयार होने पर आगे बढ़ें।',
      'Look at the picture and choose its name.':'चित्र देखें और उसका नाम चुनें।',
      'Touch two picture pieces to swap their places.':'दो टुकड़े छूकर उनकी जगह बदलें।',
      'Look at the family photo and choose the name you remember.':'परिवार की तस्वीर देखकर नाम चुनें।',
      'Enjoy your game. Take your time.':'खेल का आनंद लें। कोई जल्दी नहीं।',
      'Beautifully done!':'बहुत अच्छा किया!','You gave your brain a lovely little workout. Every effort counts.':'आपने अच्छा अभ्यास किया। हर कोशिश मायने रखती है।',
      'Saving your activity…':'आपकी गतिविधि सहेजी जा रही है…','Play again ↻':'फिर से खेलें ↻',
      'Try another game →':'दूसरा खेल खेलें →',
      'Saved to your activity history. You can play again at your own pace.':'आपकी गतिविधि सहेजी गई है। फिर से आराम से खेलें।',
      'Your next game will be a little easier. There is no rush.':'अगला खेल थोड़ा आसान होगा। कोई जल्दी नहीं।',
      'Your game finished, but this score could not be saved. Check your connection.':'खेल पूरा हुआ, लेकिन अंक सहेज नहीं पाए। इंटरनेट जाँचें।',
      'Find two matching pictures':'दो एक जैसे चित्र खोजें','Tap two cards to find a pair':'जोड़ी खोजने के लिए दो कार्ड छुएँ',
      'A good try. Have another look!':'अच्छी कोशिश! फिर से देखें।',
      'Look at these words':'ये शब्द देखें','Read the words, then press Ready when you feel ready.':'शब्द पढ़ें, फिर तैयार होने पर आगे बढ़ें।',
      "I'm ready to remember →":'मैं तैयार हूँ →',"I'm ready →":'मैं तैयार हूँ →',
      'Which words did you see?':'आपने कौन से शब्द देखे?','Check my words →':'शब्द जाँचें →',
      'Tap words to select or unselect them.':'शब्द चुनने या हटाने के लिए छुएँ।',
      'Look at this number':'यह संख्या देखें','Remember these numbers in order, then press Ready.':'संख्या का क्रम याद करें, फिर आगे बढ़ें।',
      'What was the number?':'संख्या क्या थी?','Type the numbers in the order you remember.':'याद आया क्रम टाइप करें।',
      'Your remembered number':'आपको याद संख्या','Check my memory →':'जवाब जाँचें →',
      'Name the picture':'चित्र का नाम','What do you see in this picture?':'इस चित्र में क्या दिखता है?',
      'Wonderful!':'बहुत बढ़िया!','Put the picture back together':'चित्र फिर से जोड़ें',
      'Tap two pieces to swap them, or drag one onto another.':'दो टुकड़े छुएँ या खींचकर जगह बदलें।',
      'Use the little picture above as your guide.':'ऊपर का छोटा चित्र देखकर जोड़ें।',
      'You completed the picture!':'आपने चित्र पूरा कर लिया!',
      'Family memories':'परिवार की यादें','Photos come first':'पहले तस्वीरें जोड़ें',
      'Ask your approved caregiver to add family photos to your family space.':'अपने देखभालकर्ता से परिवार की तस्वीरें जोड़ने को कहें।',
      'Go to family space →':'परिवार की तस्वीरें देखें →',
      'Remember the relationship':'रिश्ता याद करें','Who is in this photo?':'इस तस्वीर में कौन है?',
      'Take your time remembering.':'आराम से याद करें।',
      'Remember a familiar face':'परिचित चेहरा याद करें',
      'It’s okay if you don’t remember straight away.':'तुरंत याद न आए तो भी ठीक है।',
      "It's okay if you don't remember straight away.":'तुरंत याद न आए तो भी ठीक है।',
      "I'm not sure":'मुझे पक्का याद नहीं',
      'Apple':'सेब','Dog':'कुत्ता','Bicycle':'साइकिल','Sunflower':'सूरजमुखी','Cup':'कप','Elephant':'हाथी',
      'Books':'किताबें','Banana':'केला','Watch':'घड़ी','Bus':'बस','Gift':'उपहार','Kite':'पतंग',
      'flower':'फूल','garden':'बगीचा','apple':'सेब','friend':'दोस्त','music':'संगीत',
      'sunshine':'धूप','river':'नदी','family':'परिवार','bird':'पक्षी','smile':'मुस्कान',
      'moon':'चाँद','house':'घर','orange':'संतरा','pencil':'पेंसिल','window':'खिड़की','book':'किताब',
      'Daughter':'बेटी','Son':'बेटा','Granddaughter':'पोती/नातिन','Grandson':'पोता/नाती','Sister':'बहन',
      'Brother':'भाई','Wife':'पत्नी','Husband':'पति','Friend':'दोस्त','Niece':'भांजी/भतीजी',
      'Nephew':'भांजा/भतीजा','Caregiver':'देखभालकर्ता',
      'Memory cards':'याददाश्त के कार्ड','Picture to recognise':'पहचानने के लिए चित्र',
      'Garden picture puzzle':'बगीचे का चित्र-पहेली','Familiar family member':'परिवार का परिचित व्यक्ति',
      'A familiar family photo':'परिवार की तस्वीर'
    },
    kn: {
      'Gentle':'ಸರಳ','Growing':'ಬೆಳೆಯುವ','Challenge':'ಸವಾಲು','level':'ಹಂತ',
      'Take your time':'ನಿಧಾನವಾಗಿ ಆಡಿ','Find two cards with matching pictures.':'ಹೊಂದುವ ಎರಡು ಚಿತ್ರಗಳನ್ನು ಹುಡುಕಿ.',
      'Take a moment to remember the words. Press ready when you feel comfortable.':'ಪದಗಳನ್ನು ನೆನಪಿಡಿ. ಸಿದ್ಧವಾದಾಗ ಮುಂದುವರಿಯಿರಿ.',
      'Look at the number sequence. Press ready when you want to try.':'ಸಂಖ್ಯೆಗಳ ಕ್ರಮ ನೋಡಿ. ಸಿದ್ಧವಾದಾಗ ಮುಂದುವರಿಯಿರಿ.',
      'Look at the picture and choose its name.':'ಚಿತ್ರ ನೋಡಿ ಅದರ ಹೆಸರು ಆಯ್ಕೆ ಮಾಡಿ.',
      'Touch two picture pieces to swap their places.':'ಎರಡು ತುಣುಕುಗಳನ್ನು ಮುಟ್ಟಿ ಸ್ಥಾನ ಬದಲಿಸಿ.',
      'Look at the family photo and choose the name you remember.':'ಕುಟುಂಬದ ಚಿತ್ರ ನೋಡಿ ಹೆಸರು ಆಯ್ಕೆ ಮಾಡಿ.',
      'Enjoy your game. Take your time.':'ಆಟವನ್ನು ಆನಂದಿಸಿ. ಆತುರ ಬೇಡ.',
      'Beautifully done!':'ತುಂಬಾ ಚೆನ್ನಾಗಿದೆ!',
      'You gave your brain a lovely little workout. Every effort counts.':'ನೀವು ಚೆನ್ನಾಗಿ ಅಭ್ಯಾಸ ಮಾಡಿದ್ದೀರಿ. ಪ್ರತಿ ಪ್ರಯತ್ನವೂ ಮುಖ್ಯ.',
      'Saving your activity…':'ನಿಮ್ಮ ಚಟುವಟಿಕೆ ಉಳಿಸಲಾಗುತ್ತಿದೆ…',
      'Play again ↻':'ಮತ್ತೆ ಆಡಿ ↻','Try another game →':'ಇನ್ನೊಂದು ಆಟ →',
      'Saved to your activity history. You can play again at your own pace.':'ನಿಮ್ಮ ಚಟುವಟಿಕೆ ಉಳಿಸಲಾಗಿದೆ. ಮತ್ತೆ ನಿಮ್ಮ ವೇಗದಲ್ಲಿ ಆಡಿ.',
      'Your next game will be a little easier. There is no rush.':'ಮುಂದಿನ ಆಟ ಸ್ವಲ್ಪ ಸುಲಭವಾಗುತ್ತದೆ. ಆತುರ ಬೇಡ.',
      'Your game finished, but this score could not be saved. Check your connection.':'ಆಟ ಮುಗಿದಿದೆ, ಆದರೆ ಅಂಕ ಉಳಿಸಲಾಗಿಲ್ಲ. ಸಂಪರ್ಕ ಪರಿಶೀಲಿಸಿ.',
      'Find two matching pictures':'ಹೊಂದುವ ಎರಡು ಚಿತ್ರ ಹುಡುಕಿ','Tap two cards to find a pair':'ಜೋಡಿಗಾಗಿ ಎರಡು ಕಾರ್ಡ್‌ಗಳನ್ನು ಮುಟ್ಟಿ',
      'A good try. Have another look!':'ಒಳ್ಳೆಯ ಪ್ರಯತ್ನ! ಮತ್ತೊಮ್ಮೆ ನೋಡಿ.',
      'Look at these words':'ಈ ಪದಗಳನ್ನು ನೋಡಿ','Read the words, then press Ready when you feel ready.':'ಪದಗಳನ್ನು ಓದಿ, ಸಿದ್ಧವಾದಾಗ ಮುಂದುವರಿಯಿರಿ.',
      "I'm ready to remember →":'ನಾನು ಸಿದ್ಧ →',"I'm ready →":'ನಾನು ಸಿದ್ಧ →',
      'Which words did you see?':'ಯಾವ ಪದಗಳನ್ನು ನೋಡಿದಿರಿ?','Check my words →':'ಪದಗಳನ್ನು ಪರಿಶೀಲಿಸಿ →',
      'Tap words to select or unselect them.':'ಪದವನ್ನು ಆರಿಸಲು ಅಥವಾ ಬಿಡಲು ಮುಟ್ಟಿ.',
      'Look at this number':'ಈ ಸಂಖ್ಯೆಯನ್ನು ನೋಡಿ',
      'Remember these numbers in order, then press Ready.':'ಸಂಖ್ಯೆಗಳ ಕ್ರಮ ನೆನಪಿಡಿ, ನಂತರ ಮುಂದುವರಿಯಿರಿ.',
      'What was the number?':'ಸಂಖ್ಯೆ ಏನಿತ್ತು?','Type the numbers in the order you remember.':'ನೆನಪಿರುವ ಕ್ರಮದಲ್ಲಿ ಸಂಖ್ಯೆಗಳು ನಮೂದಿಸಿ.',
      'Your remembered number':'ನಿಮಗೆ ನೆನಪಿರುವ ಸಂಖ್ಯೆ','Check my memory →':'ಉತ್ತರ ಪರಿಶೀಲಿಸಿ →',
      'Name the picture':'ಚಿತ್ರಕ್ಕೆ ಹೆಸರು','What do you see in this picture?':'ಈ ಚಿತ್ರದಲ್ಲಿ ಏನು ಕಾಣುತ್ತದೆ?',
      'Wonderful!':'ಅದ್ಭುತ!','Put the picture back together':'ಚಿತ್ರವನ್ನು ಮತ್ತೆ ಜೋಡಿಸಿ',
      'Tap two pieces to swap them, or drag one onto another.':'ಎರಡು ತುಣುಕು ಮುಟ್ಟಿ ಅಥವಾ ಎಳೆದು ಸ್ಥಾನ ಬದಲಿಸಿ.',
      'Use the little picture above as your guide.':'ಮೇಲಿನ ಚಿಕ್ಕ ಚಿತ್ರವನ್ನು ನೋಡಿ.',
      'You completed the picture!':'ನೀವು ಚಿತ್ರವನ್ನು ಪೂರ್ಣಗೊಳಿಸಿದ್ದೀರಿ!',
      'Family memories':'ಕುಟುಂಬದ ನೆನಪು','Photos come first':'ಮೊದಲು ಚಿತ್ರಗಳನ್ನು ಸೇರಿಸಿ',
      'Ask your approved caregiver to add family photos to your family space.':'ಆರೈಕೆದಾರರಿಗೆ ಕುಟುಂಬದ ಚಿತ್ರ ಸೇರಿಸಲು ಹೇಳಿ.',
      'Go to family space →':'ಕುಟುಂಬದ ಚಿತ್ರಗಳಿಗೆ ಹೋಗಿ →',
      'Remember the relationship':'ಸಂಬಂಧ ನೆನಪಿಡಿ','Who is in this photo?':'ಈ ಚಿತ್ರದಲ್ಲಿ ಯಾರಿದ್ದಾರೆ?',
      'Take your time remembering.':'ನಿಧಾನವಾಗಿ ನೆನಪಿಸಿಕೊಳ್ಳಿ.','Remember a familiar face':'ಪರಿಚಿತ ಮುಖ ನೆನಪಿಡಿ',
      'It’s okay if you don’t remember straight away.':'ತಕ್ಷಣ ನೆನಪಾಗದಿದ್ದರೂ ಪರವಾಗಿಲ್ಲ.',
      "It's okay if you don't remember straight away.":'ತಕ್ಷಣ ನೆನಪಾಗದಿದ್ದರೂ ಪರವಾಗಿಲ್ಲ.',
      "I'm not sure":'ಖಚಿತವಾಗಿ ಗೊತ್ತಿಲ್ಲ',
      'Apple':'ಸೇಬು','Dog':'ನಾಯಿ','Bicycle':'ಸೈಕಲ್','Sunflower':'ಸೂರ್ಯಕಾಂತಿ','Cup':'ಕಪ್','Elephant':'ಆನೆ',
      'Books':'ಪುಸ್ತಕಗಳು','Banana':'ಬಾಳೆಹಣ್ಣು','Watch':'ಗಡಿಯಾರ','Bus':'ಬಸ್','Gift':'ಉಡುಗೊರೆ','Kite':'ಗಾಳಿಪಟ',
      'flower':'ಹೂವು','garden':'ತೋಟ','apple':'ಸೇಬು','friend':'ಗೆಳೆಯ','music':'ಸಂಗೀತ','sunshine':'ಬಿಸಿಲು',
      'river':'ನದಿ','family':'ಕುಟುಂಬ','bird':'ಹಕ್ಕಿ','smile':'ನಗು','moon':'ಚಂದ್ರ','house':'ಮನೆ',
      'orange':'ಕಿತ್ತಳೆ','pencil':'ಪೆನ್ಸಿಲ್','window':'ಕಿಟಕಿ','book':'ಪುಸ್ತಕ',
      'Daughter':'ಮಗಳು','Son':'ಮಗ','Granddaughter':'ಮೊಮ್ಮಗಳು','Grandson':'ಮೊಮ್ಮಗ',
      'Sister':'ಸಹೋದರಿ','Brother':'ಸಹೋದರ','Wife':'ಪತ್ನಿ','Husband':'ಪತಿ','Friend':'ಗೆಳೆಯ',
      'Niece':'ಸೋದರ ಸೊಸೆ','Nephew':'ಸೋದರಳಿಯ','Caregiver':'ಆರೈಕೆದಾರ',
      'Memory cards':'ನೆನಪಿನ ಕಾರ್ಡ್‌ಗಳು','Picture to recognise':'ಗುರುತಿಸುವ ಚಿತ್ರ',
      'Garden picture puzzle':'ತೋಟದ ಚಿತ್ರದ ಒಗಟು','Familiar family member':'ಪರಿಚಿತ ಕುಟುಂಬದ ಸದಸ್ಯ',
      'A familiar family photo':'ಕುಟುಂಬದ ಚಿತ್ರ'
    }
  };
  const lookup = dict[lang] || {};
  const translate = value => {
    if (lang === 'en') return String(value ?? '');
    const raw = String(value ?? '');
    const trimmed = raw.trim();
    if (!trimmed) return raw;
    if (Object.prototype.hasOwnProperty.call(lookup, trimmed)) return raw.replace(trimmed, lookup[trimmed]);
    let out = null;
    let match;
    if ((match = /^(\d+) of (\d+) pairs found(\. Lovely!)?$/.exec(trimmed))) {
      out = lang === 'hi' ? match[1]+' / '+match[2]+' जोड़ी मिली'+(match[3]?'। बहुत अच्छा!':'') :
        match[1]+' / '+match[2]+' ಜೋಡಿ ಸಿಕ್ಕಿವೆ'+(match[3]?'। ಚೆನ್ನಾಗಿದೆ!':'');
    } else if ((match = /^(Picture|Photo) (\d+) of (\d+)$/.exec(trimmed))) {
      out = (lang === 'hi' ? (match[1]==='Photo'?'तस्वीर ':'चित्र ') : (match[1]==='Photo'?'ಚಿತ್ರ ':'ಚಿತ್ರ '))+match[2]+' / '+match[3];
    } else if ((match = /^(\d+) moves\. Keep going at your pace!$/.exec(trimmed))) {
      out = lang === 'hi' ? match[1]+' चालें। आराम से खेलें!' : match[1]+' ನಡೆಗಳು. ನಿಧಾನವಾಗಿ ಮುಂದುವರಿಯಿರಿ!';
    } else if ((match = /^Nice try! It is (.+)\.$/.exec(trimmed))) {
      out = lang === 'hi' ? 'अच्छी कोशिश! यह '+(lookup[match[1]]||match[1])+' है।' :
        'ಒಳ್ಳೆಯ ಪ್ರಯತ್ನ! ಇದು '+(lookup[match[1]]||match[1])+'.';
    } else if ((match = /^Choose the (\d+) words you remember\. Take your time!$/.exec(trimmed))) {
      out = lang === 'hi' ? 'याद आए '+match[1]+' शब्द चुनें। आराम से।' : 'ನೆನಪಿರುವ '+match[1]+' ಪದಗಳನ್ನು ನಿಧಾನವಾಗಿ ಆರಿಸಿ.';
    } else if ((match = /^Hidden memory card (\d+)$/.exec(trimmed))) {
      out = lang === 'hi' ? 'छुपा कार्ड '+match[1] : 'ಮುಚ್ಚಿದ ಕಾರ್ಡ್ '+match[1];
    } else if ((match = /^Picture tile (\d+)(, selected)?$/.exec(trimmed))) {
      out = lang === 'hi' ? 'चित्र का टुकड़ा '+match[1]+(match[2]?', चुना गया':'') :
        'ಚಿತ್ರದ ತುಣುಕು '+match[1]+(match[2]?', ಆಯ್ಕೆಮಾಡಿದೆ':'');
    } else if ((match = /^Well done! Your next game will have a new, gentle challenge at the (.+) level\.$/.exec(trimmed))) {
      out = lang === 'hi' ? 'शाबाश! अगला खेल '+(lookup[match[1]]||match[1])+' स्तर का होगा।' :
        'ಚೆನ್ನಾಗಿದೆ! ಮುಂದಿನ ಆಟ '+(lookup[match[1]]||match[1])+' ಹಂತದಲ್ಲಿರುತ್ತದೆ.';
    }
    if (out) return raw.replace(trimmed,out);
    return raw;
  };

  // Translate just the game UI, never the trusted contact's stored names or answer keys.
  function updateNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const translated = translate(node.nodeValue);
      if (node.nodeValue !== translated) node.nodeValue = translated;
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.hasAttribute('aria-label')) {
      const old = node.getAttribute('aria-label'), next = translate(old);
      if (old !== next) node.setAttribute('aria-label', next);
    }
    for (const child of node.childNodes) updateNode(child);
  }
  let updating = false;
  const observer = new MutationObserver(() => {
    if (updating) return;
    updating = true;
    try {updateNode(root);} finally {updating = false;}
  });
  if (lang !== 'en') {
    updateNode(root);
    observer.observe(root,{childList:true,characterData:true,subtree:true});
  }
  window.MindCareGameTranslate = translate;
})();
