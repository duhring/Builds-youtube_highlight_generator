(function(){
  const player = document.getElementById('player');
  if(!player) return;
  function playFrom(el){
    const t = Number(el?.dataset?.start || 0);
    if(Number.isFinite(t)){ player.currentTime = t; player.play(); window.scrollTo({top:0, behavior:'smooth'}); }
  }
  document.addEventListener('click', (e) => {
    const card = e.target.closest('[data-start]');
    if(card) playFrom(card);
  });
  document.addEventListener('keydown', (e)=>{
    if(e.key === 'Enter' && document.activeElement?.hasAttribute('data-start')){
      e.preventDefault(); playFrom(document.activeElement);
    }
  });
})();