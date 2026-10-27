(()=>{
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const revealTargets=document.querySelectorAll('main .hero,main .sport-hero,main .f1-showcase-hero,main .f1-stat,main .section-head,main .match-card,main .race-card,main .session-card,main .result-card,main .feature');
  if(!reduced&&'IntersectionObserver'in window){
    document.documentElement.classList.add('has-motion');
    revealTargets.forEach((element,index)=>{element.classList.add('js-reveal');element.style.transitionDelay=`${Math.min(index%4,3)*55}ms`});
    const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');observer.unobserve(entry.target)}}),{threshold:.12,rootMargin:'0px 0px -24px 0px'});
    revealTargets.forEach(element=>observer.observe(element));
  }
  if(!reduced&&window.matchMedia('(pointer: fine)').matches){
    document.querySelectorAll('.f1-showcase-hero').forEach(hero=>hero.addEventListener('pointermove',event=>{const rect=hero.getBoundingClientRect();hero.style.setProperty('--pointer-x',`${event.clientX-rect.left}px`);hero.style.setProperty('--pointer-y',`${event.clientY-rect.top}px`)}));
    document.querySelectorAll('.match-card,.race-card,.f1-stat').forEach(card=>{
      card.classList.add('js-tilt');
      card.addEventListener('pointermove',event=>{const rect=card.getBoundingClientRect();const x=(event.clientX-rect.left)/rect.width-.5;const y=(event.clientY-rect.top)/rect.height-.5;card.style.transform=`perspective(900px) rotateY(${x*4}deg) rotateX(${-y*4}deg) translateY(-2px)`});
      card.addEventListener('pointerleave',()=>{card.style.transform=''});
    });
  }
  document.querySelectorAll('.js-count').forEach(element=>{
    const finalValue=Number(element.dataset.value);if(!Number.isFinite(finalValue)||finalValue<0)return;
    let done=false;
    const animate=()=>{if(done)return;done=true;const start=performance.now(),duration=700;const step=now=>{const progress=Math.min(1,(now-start)/duration);element.textContent=Math.round(finalValue*(1-Math.pow(1-progress,3))).toLocaleString();if(progress<1)requestAnimationFrame(step)};requestAnimationFrame(step)};
    if(reduced||!('IntersectionObserver'in window)){animate();return}const countObserver=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){animate();countObserver.disconnect()}},{threshold:.8});countObserver.observe(element);
  });
})();
