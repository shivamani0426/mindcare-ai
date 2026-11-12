(() => {
  'use strict';
  const root = document.getElementById('game-root');
  if (!root) return;
  const game = root.dataset.game;
  const level = Math.max(1,Math.min(3,Number(root.dataset.level) || 1));
  const levelNames = {1:'Gentle',2:'Growing',3:'Challenge'};
  let family = [];
  try { family = JSON.parse(root.dataset.family || '[]'); } catch (_) { /* empty */ }
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let started = 0;
  let mistakes = 0;
  const escapeHTML = (val) => String(val ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const shuffle = (arr) => {
    const a = [...arr];
    for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];}
    return a;
  };
  const toolbar = (instruction, status='Take your time') => `<div class="game-toolbar"><strong>🌱 ${escapeHTML(instruction)}</strong><span>${escapeHTML(status)} · ${levelNames[level]} level</span></div>`;
  const say = message => window.MindCareVoice?.speak(message);
  const button = (text, id, secondary=false) => `<button type="button" class="button ${secondary?'button-outline':'button-primary'} button-lg" id="${id}">${text}</button>`;
  const init = () => {
    started=Date.now();mistakes=0;
    ({cards,words,numbers,pictures,puzzle,family:familyGame}[game] || cards)();
    const help = {cards:'Find two cards with matching pictures.',words:'Take a moment to remember the words. Press ready when you feel comfortable.',numbers:'Look at the number sequence. Press ready when you want to try.',pictures:'Look at the picture and choose its name.',puzzle:'Touch two picture pieces to swap their places.',family:'Look at the family photo and choose the name you remember.'};
    say(help[game] || 'Enjoy your game. Take your time.');
  };
  root.querySelector('#begin-game')?.addEventListener('click', init);
  async function finish(score) {
    score = Math.max(0,Math.min(100,Math.round(score)));
    const seconds = Math.max(1,Math.min(3600,Math.round((Date.now()-started)/1000)));
    root.innerHTML = `<div class="game-result"><span class="game-result-icon">🌻</span><h2>Beautifully done!</h2><strong>${score}%</strong><p>You gave your brain a lovely little workout. Every effort counts.</p><p id="save-status" role="status">Saving your activity…</p><div class="result-actions">${button('Play again ↻','again') }<a class="button button-outline button-lg" href="/games">Try another game →</a></div></div>`;
    root.querySelector('#again')?.addEventListener('click', () => window.location.reload());
    try {
      const response = await fetch('/api/games/finish', {
        method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},credentials:'same-origin',
        body:JSON.stringify({game,score,mistakes,seconds,difficulty:level})
      });
      if (!response.ok) throw Error('Not saved');
      const data=await response.json();
      let message='Saved to your activity history. You can play again at your own pace.';
      if (data.level_change>0) message='Well done! Your next game will have a new, gentle challenge at the '+data.next_level_name+' level.';
      if (data.level_change<0) message='Your next game will be a little easier. There is no rush.';
      root.querySelector('#save-status').textContent='✓ '+message;
      say(message);
    } catch (_) {
      root.querySelector('#save-status').textContent = 'Your game finished, but this score could not be saved. Check your connection.';
    }
  }
  function cards() {
    const symbols = ['🌻','🍎','🧸','🐢','🎈','🌈','🦋','⭐'];
    const pairs = [3,5,8][level-1];
    const deck = shuffle(symbols.slice(0,pairs).flatMap((s,i)=>[{i,s},{i,s}]));
    let revealed = [],matched = new Set(),busy=false;
    root.innerHTML = toolbar('Find two matching pictures') + `<p class="game-instructions">Tap two cards to find a pair</p><div class="memory-grid" id="memory-board" aria-label="Memory cards"></div><p class="game-message" id="game-message">0 of ${pairs} pairs found</p>`;
    const board=root.querySelector('#memory-board');
    board.style.gridTemplateColumns=`repeat(${pairs===3?3:4},minmax(0,1fr))`;
    if(pairs===8) board.classList.add('memory-grid-advanced');
    deck.forEach((card,index)=> {
      const el=document.createElement('button');el.type='button';el.className='memory-card';el.dataset.index=String(index);el.textContent='✦';el.setAttribute('aria-label','Hidden memory card '+(index+1));
      el.addEventListener('click',()=>{
        if(busy||revealed.includes(index)||matched.has(index))return;
        el.textContent=card.s;el.classList.add('is-open');el.setAttribute('aria-label',card.s);
        revealed.push(index);
        if(revealed.length===2){
          const [a,b]=revealed;
          if(deck[a].i===deck[b].i){matched.add(a);matched.add(b);revealed=[];board.children[a].classList.add('is-matched');board.children[b].classList.add('is-matched');board.children[a].disabled=true;board.children[b].disabled=true;
            root.querySelector('#game-message').textContent=`${matched.size/2} of ${pairs} pairs found. Lovely!`;
            if(matched.size===deck.length)setTimeout(()=>finish(Math.max(0,100-Math.round(mistakes*100/(pairs*2.5)))),650);
          }else{mistakes++;busy=true;root.querySelector('#game-message').textContent='A good try. Have another look!';
            setTimeout(()=>{for(const n of revealed){const btn=board.children[n];btn.textContent='✦';btn.classList.remove('is-open');btn.setAttribute('aria-label','Hidden memory card '+(n+1));}revealed=[];busy=false;},950);
          }
        }
      });board.appendChild(el);
    });
  }
  function words() {
    const pool=['flower','garden','apple','friend','music','sunshine','river','family','bird','smile','moon','house','orange','pencil','window','book'];
    const count=[3,5,7][level-1];
    const targets=shuffle(pool).slice(0,count);
    root.innerHTML=toolbar('Look at these words')+`<p class="game-instructions">Read the words, then press Ready when you feel ready.</p><div class="word-display">${targets.map(w=>`<span>${w}</span>`).join('')}</div><div class="center-actions">${button("I'm ready to remember →",'ready')}</div>`;
    root.querySelector('#ready').addEventListener('click',()=>{
      const choices=shuffle([...targets,...shuffle(pool.filter(p=>!targets.includes(p))).slice(0,count+2)]);
      const selected=new Set();
      root.innerHTML=toolbar('Which words did you see?')+`<p class="game-instructions">Choose the ${count} words you remember. Take your time!</p><div class="choice-grid">${choices.map((w,i)=>`<button type="button" class="choice" data-word="${w}">${w}</button>`).join('')}</div><div class="center-actions">${button('Check my words →','check-words')}</div><p class="game-message">Tap words to select or unselect them.</p>`;
      root.querySelectorAll('[data-word]').forEach(el=>el.addEventListener('click',()=>{
        const val=el.dataset.word;if(selected.has(val)){selected.delete(val);el.classList.remove('selected');el.setAttribute('aria-pressed','false');}
        else{selected.add(val);el.classList.add('selected');el.setAttribute('aria-pressed','true');}
      }));
      root.querySelector('#check-words').addEventListener('click',()=>{
        const correct=targets.filter(w=>selected.has(w)).length;
        const extra=[...selected].filter(w=>!targets.includes(w)).length;
        mistakes=count-correct+extra;
        finish(Math.max(0,Math.round((correct-extra*.5)/count*100)));
      });
    });
  }
  function numbers() {
    const count=[4,6,8][level-1];
    const seq=Array.from({length:count},()=>Math.floor(Math.random()*9)+1).join('');
    root.innerHTML=toolbar('Look at this number')+`<p class="game-instructions">Remember these numbers in order, then press Ready.</p><div class="number-display">${seq}</div><div class="center-actions">${button("I'm ready →",'ready')}</div>`;
    root.querySelector('#ready').addEventListener('click',()=>{
      root.innerHTML=toolbar('What was the number?')+`<p class="game-instructions">Type the numbers in the order you remember.</p><label for="sequence-answer" class="game-message">Your remembered number</label><input id="sequence-answer" class="game-answer" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="${count}" autocomplete="off" aria-label="Numbers you remember"><div class="center-actions">${button('Check my memory →','check-number')}</div>`;
      root.querySelector('#check-number').addEventListener('click',()=>{
        const input=root.querySelector('#sequence-answer').value.replace(/\D/g,'').slice(0,count);
        const match=[...seq].filter((digit,i)=>digit===input[i]).length;
        mistakes=count-match;finish((match/count)*100);
      });
      root.querySelector('#sequence-answer').focus();
    });
  }
  function pictures() {
    const objects=[['🍎','Apple'],['🐕','Dog'],['🚲','Bicycle'],['🌻','Sunflower'],['☕','Cup'],['🐘','Elephant'],['📚','Books'],['🍌','Banana'],['⌚','Watch'],['🚌','Bus'],['🎁','Gift'],['🪁','Kite']];
    const roundCount=[3,5,6][level-1];
    const rounds=shuffle(objects).slice(0,roundCount);let round=0,correct=0;
    const show=()=>{
      if(round===rounds.length){finish(correct/rounds.length*100);return;}
      const [emoji,label]=rounds[round];const choices=shuffle([label,...shuffle(objects.map(x=>x[1]).filter(n=>n!==label)).slice(0,level)]);
      root.innerHTML=toolbar('Name the picture',`Picture ${round+1} of ${rounds.length}`)+`<p class="game-instructions">What do you see in this picture?</p><div class="big-picture" role="img" aria-label="Picture to recognise">${emoji}</div><div class="choice-grid">${choices.map((name,i)=>`<button type="button" class="choice" data-answer="${escapeHTML(name)}">${escapeHTML(name)}</button>`).join('')}</div><p id="picture-feedback" class="game-message"></p>`;
      root.querySelectorAll('[data-answer]').forEach(btn=>btn.addEventListener('click',()=>{
        if(root.querySelector('.choice:disabled'))return;
        const right=btn.dataset.answer===label;if(right){correct++;btn.classList.add('correct');}else{mistakes++;btn.classList.add('wrong');}
        root.querySelectorAll('[data-answer]').forEach(x=>x.disabled=true);
        root.querySelector('#picture-feedback').textContent=right?'Wonderful!':'Nice try! It is '+label+'.';
        setTimeout(()=>{round++;show();},1050);
      }));
    };show();
  }
  function puzzle() {
    const size=[2,3,4][level-1];
    const total=size*size;
    let tiles=shuffle(Array.from({length:total},(_,i)=>i));
    if(tiles.every((v,i)=>v===i))[tiles[0],tiles[1]]=[tiles[1],tiles[0]];
    // Minimum number of swaps needed to solve this permutation. Extra moves
    // are an understandable feedback measure, unlike counting moves that
    // temporarily move a tile away from its correct position.
    const visited=new Set();let cycles=0;
    for(let i=0;i<total;i++){
      if(visited.has(i))continue;
      cycles++;let j=i;
      while(!visited.has(j)){visited.add(j);j=tiles[j];}
    }
    const optimalSwaps=total-cycles;
    let selected=null,moves=0;
    root.innerHTML=toolbar('Put the picture back together')+`<p class="game-instructions">Tap two pieces to swap them, or drag one onto another.</p><img class="puzzle-reference" src="/static/garden.svg" alt="Reference picture: a bright garden with a house and a tree"><div class="puzzle-grid" id="puzzle-board" role="group" aria-label="Garden picture puzzle"></div><p id="puzzle-status" class="game-message">Use the little picture above as your guide.</p>`;
    const board=root.querySelector('#puzzle-board');board.style.gridTemplateColumns=`repeat(${size},1fr)`;
    const swap=(a,b)=>{
      if(a===b){selected=null;render();return;}
      [tiles[a],tiles[b]]=[tiles[b],tiles[a]];moves++;
      mistakes=Math.max(0,moves-optimalSwaps);
      selected=null;render();
      if(tiles.every((v,i)=>v===i)){root.querySelector('#puzzle-status').textContent='You completed the picture!';setTimeout(()=>finish(Math.max(0,100-mistakes*[12,7,4][level-1])),700);}
    };
    function render(){
      board.innerHTML='';
      tiles.forEach((piece,i)=>{
        const b=document.createElement('button');b.type='button';b.draggable=true;b.className='puzzle-tile'+(selected===i?' selected':'');
        b.setAttribute('aria-label','Picture tile '+(i+1)+(selected===i?', selected':''));
        b.style.backgroundImage='url(/static/garden.svg)';b.style.backgroundSize=`${size*100}% ${size*100}%`;
        const col=piece%size,row=Math.floor(piece/size);
        b.style.backgroundPosition=`${col/(size-1)*100}% ${row/(size-1)*100}%`;
        b.addEventListener('click',()=>{if(selected===null){selected=i;render();}else swap(selected,i);});
        b.addEventListener('dragstart',ev=>{ev.dataTransfer?.setData('text/plain',String(i));});
        b.addEventListener('dragover',ev=>ev.preventDefault());
        b.addEventListener('drop',ev=>{ev.preventDefault();const n=Number(ev.dataTransfer?.getData('text/plain'));if(Number.isInteger(n)&&n>=0&&n<total)swap(n,i);});
        board.appendChild(b);
      });
      root.querySelector('#puzzle-status').textContent=moves+' moves. Keep going at your pace!';
    }
    render();
  }
  function familyGame() {
    if(!family.length){root.innerHTML=toolbar('Family memories')+`<div class="empty-small"><span>💛</span><h2>Photos come first</h2><p>Ask your approved caregiver to add family photos to your family space.</p><a class="button button-outline" href="/family">Go to family space →</a></div>`;return;}
    const rounds=shuffle(family).slice(0,Math.min([2,3,5][level-1],family.length));
    let index=0,correct=0,questions=0;
    const relationOptions=['Daughter','Son','Granddaughter','Grandson','Sister','Brother','Wife','Husband','Friend','Niece','Nephew','Caregiver'];
    const endQuestion=(right,answer,feedbackId)=>{
      questions++;
      if(right) correct++; else mistakes++;
      root.querySelectorAll('[data-answer]').forEach(b=>b.disabled=true);
      const feedback=root.querySelector('#'+feedbackId);
      if(feedback)feedback.textContent=answer;
    };
    const nextRound=()=>{index++;show();};
    const askRelation=(person)=>{
      const distractors=shuffle([...new Set([...family.filter(m=>m.id!==person.id).map(m=>m.relation),...relationOptions])]
        .filter(x=>x.toLowerCase()!==person.relation.toLowerCase())).slice(0,level===2?2:3);
      const choices=shuffle([person.relation,...distractors]);
      root.innerHTML=toolbar('Remember the relationship',`Photo ${index+1} of ${rounds.length}`)+
        `<p class="game-instructions">How is ${escapeHTML(person.name)} connected to you?</p>`+
        `<img class="family-picture" src="${escapeHTML(person.image)}" alt="Familiar family member">`+
        `<div class="choice-grid">${choices.map(name=>`<button type="button" class="choice" data-answer="${escapeHTML(name)}">${escapeHTML(name)}</button>`).join('')}</div>`+
        `<p class="game-message" id="family-feedback">Take your time remembering.</p>`;
      root.querySelectorAll('[data-answer]').forEach(btn=>btn.addEventListener('click',()=>{
        if(root.querySelector('[data-answer]:disabled'))return;
        const right=btn.dataset.answer===person.relation;
        btn.classList.add(right?'correct':'wrong');
        endQuestion(right,`${person.name} is your ${person.relation}. 💛`,'family-feedback');
        setTimeout(nextRound,1700);
      }));
    };
    function show(){
      if(index===rounds.length){finish(questions?correct/questions*100:0);return;}
      const person=rounds[index];
      const other=shuffle([...new Set(family.filter(m=>m.id!==person.id).map(m=>m.name))]).slice(0,level);
      const choices=shuffle([person.name,...other,...(other.length===0?["I'm not sure"]:[])]);
      root.innerHTML=toolbar('Remember a familiar face',`Photo ${index+1} of ${rounds.length}`)+
        `<p class="game-instructions">Who is in this photo?</p><img class="family-picture" src="${escapeHTML(person.image)}" alt="A familiar family photo">`+
        `<div class="choice-grid">${choices.map(name=>`<button type="button" class="choice" data-answer="${escapeHTML(name)}">${escapeHTML(name)}</button>`).join('')}</div>`+
        `<p class="game-message" id="family-feedback">It's okay if you don't remember straight away.</p>`;
      root.querySelectorAll('[data-answer]').forEach(btn=>btn.addEventListener('click',()=>{
        if(root.querySelector('[data-answer]:disabled'))return;
        const right=btn.dataset.answer===person.name;
        btn.classList.add(right?'correct':'wrong');
        endQuestion(right,`This is ${person.name}, your ${person.relation}. 💛`,'family-feedback');
        setTimeout(()=>{if(level>=2)askRelation(person);else nextRound();},1800);
      }));
    }
    show();
  }
})();
