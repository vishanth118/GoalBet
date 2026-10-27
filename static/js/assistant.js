(()=>{
  const root=document.getElementById('assistant-root'); if(!root)return;
  const toggle=document.getElementById('assistant-toggle'),panel=document.getElementById('assistant-panel'),close=document.getElementById('assistant-close'),form=document.getElementById('assistant-form'),input=document.getElementById('assistant-input'),messages=document.getElementById('assistant-messages'),status=document.getElementById('assistant-status');
  const token=document.querySelector('meta[name="csrf-token"]')?.content||'';
  const open=()=>{panel.hidden=false;toggle.setAttribute('aria-expanded','true');input.focus()};
  const shut=()=>{panel.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.focus()};
  toggle.addEventListener('click',()=>panel.hidden?open():shut());close.addEventListener('click',shut);
  document.querySelectorAll('.ask-assistant').forEach(button=>button.addEventListener('click',open));
  const add=(text,kind='assistant-message')=>{const p=document.createElement('p');p.className=`assistant-message ${kind}`;p.textContent=text;messages.appendChild(p);messages.scrollTop=messages.scrollHeight;return p};
  const sendFeedback=async(id,helpful)=>{const response=await fetch(root.dataset.feedbackUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify({conversation_id:id,helpful})});const data=await response.json();if(!response.ok)throw new Error(data.message||'Feedback could not be saved right now.');return data};
  form.addEventListener('submit',async event=>{event.preventDefault();const message=input.value.trim();if(!message)return;add(message,'assistant-message assistant-user');input.value='';status.textContent='Getting an answer…';form.querySelector('button').disabled=true;
    try{const response=await fetch(root.dataset.chatUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify({message})});const data=await response.json();if(!response.ok)throw new Error(data.error||'The assistant is temporarily unavailable.');add(data.answer);const controls=document.createElement('div');controls.className='assistant-feedback';for(const [label,value] of [['Helpful',true],['Not helpful',false]]){const b=document.createElement('button');b.type='button';b.textContent=label;b.addEventListener('click',async()=>{try{await sendFeedback(data.conversation_id,value);controls.textContent='Thanks for your feedback.'}catch{controls.textContent='Feedback could not be saved right now.'}});controls.appendChild(b)}messages.appendChild(controls);messages.scrollTop=messages.scrollHeight;status.textContent='';}
    catch(error){add(error.message);status.textContent='Please try again or contact Support.'}finally{form.querySelector('button').disabled=false;input.focus()}
  });
})();
