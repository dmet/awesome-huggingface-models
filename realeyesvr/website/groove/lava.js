/* Implicit wax surface + semantic HTML controls. No dependencies. */
(() => {
  const lamp = document.querySelector('.lamp');
  const surface = document.createElement('div');
  surface.className = 'wax-surface';
  surface.innerHTML = '<canvas aria-hidden="true"></canvas><div class="wax-labels" role="group" aria-label="Create"></div>';
  lamp.append(surface);
  const canvas = surface.querySelector('canvas'), ctx = canvas.getContext('2d');
  if (!ctx) { surface.remove(); return; }
  lamp.classList.add('metaball-lamp');
  // Feather the actual sloping vessel outline, rather than blurring the wax
  // or just fading the rectangular canvas corners. Shared by both liquid layers.
  const edgeMask=document.createElement('canvas');
  edgeMask.width=256;edgeMask.height=336;
  const maskContext=edgeMask.getContext('2d');
  if(maskContext){
    const w=edgeMask.width,h=edgeMask.height;
    const outline=[[.25,0],[.75,0],[1,.78],[.98,.88],[.88,1],[.12,1],[.02,.88],[0,.78]].map(([x,y])=>[x*w,y*h]);
    const pixels=maskContext.createImageData(w,h);
    for(let y=0;y<h;y++)for(let x=0;x<w;x++){
      const px=x+.5,py=y+.5;let inside=true,distance=Infinity;
      for(let i=0;i<outline.length;i++){
        const [ax,ay]=outline[i],[bx,by]=outline[(i+1)%outline.length];
        const dx=bx-ax,dy=by-ay;
        if(dx*(py-ay)-dy*(px-ax)<0)inside=false;
        const t=Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)));
        distance=Math.min(distance,Math.hypot(px-ax-t*dx,py-ay-t*dy));
      }
      const fade=inside?Math.min(1,distance/(w*.045)):0;
      const k=(y*w+x)*4;
      pixels.data[k]=pixels.data[k+1]=pixels.data[k+2]=255;
      pixels.data[k+3]=Math.round(255*fade*fade*(3-2*fade));
    }
    maskContext.putImageData(pixels,0,0);
    lamp.style.setProperty('--wax-edge-mask',`url("${edgeMask.toDataURL()}")`);
  }
  const labels = surface.querySelector('.wax-labels');
  const nav = document.createElement('div');
  nav.className = 'wax-nav';
  nav.innerHTML = '<button type="button" class="wax-back" hidden>← Back</button><span class="wax-path">Create</span><button type="button" class="wax-pause" aria-pressed="false">Pause motion</button>';
  lamp.append(nav);
  const hint = document.createElement('p');
  hint.className = 'wax-hint'; hint.setAttribute('role', 'status'); lamp.append(hint);
  const colors = { amber:[255,117,25], pink:[228,49,187], purple:[125,65,235], coral:[244,87,61] };
  function validateMenu(input) {
    let total=0;
    function parse(node,depth=0,defaultColor='amber') {
      if(!node||typeof node!=='object'||Array.isArray(node)||typeof node.name!=='string'||!node.name.trim()||node.name.length>40)throw Error('Each button needs a name of 1–40 characters.');
      if(depth>8||++total>200)throw Error('Use at most 8 nested levels and 200 buttons.');
      const color=node.color??defaultColor;
      if(!Object.hasOwn(colors,color))throw Error('Colors: amber, pink, purple, coral.');
      if(node.id!==undefined&&(typeof node.id!=='string'||node.id.length>80))throw Error('Button IDs must be strings of at most 80 characters.');
      const result={name:node.name.trim(),color,id:node.id};
      if(node.children!==undefined){
        if(!Array.isArray(node.children)||!node.children.length||node.children.length>8)throw Error('Use 1–8 buttons per group; put extra choices in nested groups.');
        if(node.action!==undefined)throw Error('A button can have children or an action, not both.');
        // Keep the Groove palette at every level, reserving explicit colors first.
        const palette=Object.keys(colors);
        const used=new Set(node.children.map(child=>child?.color).filter(Boolean));
        result.children=node.children.map((child,index)=>{
          const automatic=palette.find(candidate=>!used.has(candidate))??palette[index%palette.length];
          const parsed=parse(child,depth+1,automatic);
          used.add(parsed.color);
          return parsed;
        });
      }else{
        const a=node.action??{type:'event'};
        if(!a||!['upload','style','motion','dialog','event'].includes(a.type))throw Error('Unknown button action.');
        if(a.type==='style'&&!['Desert','Dreamlike','Neon','Cinematic'].includes(a.value))throw Error('Unknown style.');
        if(a.type==='motion'&&typeof a.value!=='boolean')throw Error('Motion value must be true or false.');
        if(a.type==='dialog'&&(typeof a.text!=='string'||a.text.length>4000))throw Error('Dialog actions need text (up to 4,000 characters).');
        result.action={type:a.type,value:a.value,text:a.text};
      }
      return result;
    }
    const menu=parse(input);
    if(!menu.children)throw Error('The menu needs a children array.');
    return menu;
  }
  function activate(node){
    const a=node.action;
    if(a.type==='upload')document.querySelector('#upload').click();
    if(a.type==='style'){selected.style=a.value;updateQueue();notify(a.value+' flowed into your queue');}
    if(a.type==='motion'){selected.motion=a.value;updateQueue();notify(a.value?'Motion added':'Motion removed');}
    if(a.type==='dialog')openDialog(node.name,a.text);
    if(a.type==='event'){
      lamp.dispatchEvent(new CustomEvent('groove:select',{bubbles:true,detail:{id:node.id??node.name,name:node.name}}));
      notify(node.name+' selected');
    }
  }
  let root;
  try{root=validateMenu(JSON.parse(document.querySelector('#lamp-menu').textContent));}
  catch(error){lamp.classList.remove('metaball-lamp');surface.remove();nav.remove();hint.remove();notify('Lamp menu: '+error.message);return;}
  let path=[], bodies=[], ghosts=[], elapsed=0, last=0, paused=false, activeUntil=0, idleBlend=0, keyboardMode=false;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const back = nav.querySelector('.wax-back'), pause = nav.querySelector('.wax-pause');
  const W=192,H=252; canvas.width=W;canvas.height=H;
  const vessel=[[.25,0],[.75,0],[1,.78],[.98,.88],[.88,1],[.12,1],[.02,.88],[0,.78]];
  // Work in canvas-width units so wall normals respect the tall vessel aspect.
  const walls=vessel.map(([x,y],i)=>{
    const [bx,by]=vessel[(i+1)%vessel.length];
    const dx=bx-x,dy=(by-y)*H/W,length=Math.hypot(dx,dy);
    return {x,y:y*H/W,nx:-dy/length,ny:dx/length};
  });
  function containWax(b,dt){
    b.contact=(b.contact||0)*Math.exp(-dt*3);
    // A soft outer skin reaches the glass before the center reverses direction.
    for(let pass=0;pass<3;pass++)for(const wall of walls){
      const distance=(b.x-wall.x)*wall.nx+(b.y*H/W-wall.y)*wall.ny;
      const penetration=b.r*.92-distance;
      if(penetration<=0)continue;
      b.x+=wall.nx*penetration;b.y+=wall.ny*penetration*W/H;
      const speed=b.vx*wall.nx+b.vy*H/W*wall.ny;
      if(speed<0){
        // Low restitution feels like viscous wax, while preserving wall sliding.
        b.vx-=1.55*speed*wall.nx;b.vy-=1.55*speed*wall.ny*W/H;
      }
      b.contact=Math.min(1,Math.max(b.contact,penetration*35+Math.abs(speed)*3));
      b.nx=wall.nx;b.ny=wall.ny;
    }
  }
  const frame=ctx.createImageData(W,H);
  function show(nodes, origin={x:.5,y:.48}, focus=false) {
    ghosts=bodies.map(b=>({...b,life:1}));
    labels.replaceChildren();
    bodies=nodes.map((node,i)=>{
      const n=nodes.length, angle=-Math.PI/2+i*Math.PI*2/n;
      const columns=2, rows=Math.ceil(n/columns);
      const tx=n>4?.5+((i%columns)-.5)*.38:n===1?.5:.5+Math.cos(angle)*.23;
      const ty=n>4?.22+Math.floor(i/columns)*(.53/(rows-1)):n===1?.46:.48+Math.sin(angle)*.26;
      const b={node,x:reduced.matches||!ghosts.length?tx:origin.x,y:reduced.matches||!ghosts.length?ty:origin.y,tx,ty,vx:Math.cos(angle)*.12,vy:Math.sin(angle)*.12,r:.265/Math.sqrt(n),phase:i*1.8,life:reduced.matches||!ghosts.length?1:0};
      const button=document.createElement('button');button.className='wax-choice';
      button.style.width=(n>4?23:26)+'%';
      const text=document.createElement('span');text.textContent=node.name;
      const sub=document.createElement('small');sub.textContent=node.children?'Tap to split':'Choose';
      button.append(text,sub);button.setAttribute('aria-label',node.name+(node.children?', open choices':''));
      if(node.children)button.setAttribute('aria-expanded','false');
      button.onclick=()=>{if(node.children){path.push(node);show(node.children,{x:b.x,y:b.y},true);}else{activate(node);hint.textContent=node.name+' selected · Back brings the branches together';}};
      labels.append(button);b.button=button;return b;
    });
    if(paused||reduced.matches){ghosts=[];for(const b of bodies){b.x=b.tx;b.y=b.ty;b.life=1;}}
    back.hidden=!path.length;nav.querySelector('.wax-path').textContent=path.length?path.map(n=>n.name).join(' / '):root.name;
    labels.setAttribute('aria-label',path.at(-1)?.name||root.name);
    hint.textContent=path.length?'Double-click empty liquid to go back · or use Back':'Tap a branch to explore';
    if(focus)bodies[0].button.focus({preventScroll:true});
    draw();
  }
  back.onclick=()=>{if(!path.length)return;path.pop();show(path.length?path.at(-1).children:root.children,{x:.5,y:.48},true);};
  surface.addEventListener('dblclick',event=>{
    if(event.target.closest('button')||!path.length)return;
    event.preventDefault();back.click();
  });
  lamp.addEventListener('keydown',e=>{if(e.key==='Escape'&&path.length&&!document.querySelector('dialog[open]')){e.preventDefault();back.click();}});
  // A parked pointer or focus left behind by a click must not stop the lamp forever.
  const interact=()=>{activeUntil=performance.now()+2400;};
  // Programmatic focus after a mouse click can match :focus-visible. Only
  // genuine keyboard navigation should hold choices steady indefinitely.
  document.addEventListener('keydown',event=>{
    if(['Tab','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Enter',' '].includes(event.key))keyboardMode=true;
  },true);
  for(const event of ['pointermove','pointerdown'])lamp.addEventListener(event,()=>{keyboardMode=false;});
  for(const event of ['pointermove','pointerdown','focusin','keydown'])lamp.addEventListener(event,interact);
  pause.onclick=()=>{paused=!paused;lamp.classList.toggle('motion-paused',paused);pause.setAttribute('aria-pressed',String(paused));pause.textContent=paused?'Resume motion':'Pause motion';};
  function draw(){
    let all=[...bodies,...ghosts];
    // Even the unopened Create mass sheds and reabsorbs two small wax lobes.
    // These are decorative field sources, so the menu never navigates by itself.
    if(bodies.length===1&&!reduced.matches){
      const b=bodies[0], spread=idleBlend*(.5+.5*Math.sin(elapsed*.34));
      all=[{...b,r:b.r*Math.sqrt(.64)},...[-1,1].map((side,i)=>({
        ...b,r:b.r*Math.sqrt(.18),
        x:b.x+side*.15*spread*Math.cos(elapsed*.23),
        y:b.y+side*.24*spread,phase:b.phase+i+1
      })),...ghosts];
    }
    const data=frame.data;
    for(let y=0;y<H;y++)for(let x=0;x<W;x++){
      const px=x/W,py=y/H;let f=0,gx=0,gy=0,cr=0,cg=0,cb=0;
      for(const b of all){
        const dx=px-b.x,dy=(py-b.y)*H/W;
        const stretch=1+.12*Math.sin(elapsed*.63+b.phase);
        const squash=1+(b.contact||0)*.6;
        const nx=b.nx??1,ny=b.ny??0;
        const normal=dx*nx+dy*ny,tangent=-dx*ny+dy*nx;
        const wallShape=(squash-1)*normal*normal+(1/squash-1)*tangent*tangent;
        const d=dx*dx*stretch+dy*dy/stretch+wallShape+.0008;
        const weight=b.r*b.r*b.life/d; f+=weight;
        gx+=weight*(dx*stretch+(squash-1)*normal*nx-(1/squash-1)*tangent*ny)/d;
        gy+=weight*(dy/stretch+(squash-1)*normal*ny+(1/squash-1)*tangent*nx)/d;
        const c=colors[b.node.color];cr+=c[0]*weight;cg+=c[1]*weight;cb+=c[2]*weight;
      }
      const k=(y*W+x)*4, edge=Math.min(1,Math.max(0,(f-1)*12));
      if(f<.75){data[k+3]=0;continue;}
      const norm=Math.sqrt(gx*gx+gy*gy)+.001;
      const light=Math.max(0,(-gx*.5-gy*.8)/norm);
      const rim=Math.exp(-Math.max(0,f-1)*3.5), spec=Math.pow(light,8)*.48;
      const shade=.64+.24*light;
      data[k]=Math.min(255,cr/f*shade+rim*95+spec*180);
      data[k+1]=Math.min(255,cg/f*shade+rim*73+spec*155);
      data[k+2]=Math.min(255,cb/f*shade+rim*66+spec*150);
      data[k+3]=edge*255+(1-edge)*Math.max(0,(f-.75)*80);
    }
    ctx.putImageData(frame,0,0);
    for(const b of bodies){b.button.style.left=`${b.x*100}%`;b.button.style.top=`${b.y*100}%`;}
  }
  function tick(now){
    requestAnimationFrame(tick);
    if(now-last<40||document.hidden)return;
    const dt=Math.min((now-last)/1000,.05);last=now;
    const settled=now<activeUntil||(keyboardMode&&labels.contains(document.activeElement));
    if(!paused&&!reduced.matches){
      if(!settled)elapsed+=dt;
      idleBlend+=((settled?0:1)-idleBlend)*Math.min(1,dt*2);
      for(const b of bodies){
        // Low-frequency convection contracts the cluster; the field fuses at contact.
        b.life=Math.min(1,b.life+dt*1.8);
        const pulse=1.12+.32*Math.sin(elapsed*.31);
        const angle=elapsed*.12;
        const ox=b.tx-.5,oy=(b.ty-.48)*.8;
        const driftX=.5+(ox*Math.cos(angle)-oy*Math.sin(angle))*pulse+.095*Math.sin(elapsed*.41+b.phase);
        const driftY=.48+(ox*Math.sin(angle)+oy*Math.cos(angle))*pulse*1.4+.16*Math.sin(elapsed*.29+b.phase);
        const tx=b.tx+(driftX-b.tx)*idleBlend;
        const ty=b.ty+(driftY-b.ty)*idleBlend;
        b.vx+=(tx-b.x)*dt*3;b.vy+=(ty-b.y)*dt*3;
        b.vx*=Math.exp(-dt*3);b.vy*=Math.exp(-dt*3);b.x+=b.vx*dt;b.y+=b.vy*dt;
        containWax(b,dt);
      }
      for(const g of ghosts){g.life-=dt*1.8;g.x+=(.5-g.x)*dt*3;g.y+=(.48-g.y)*dt*3;}
      ghosts=ghosts.filter(g=>g.life>0);
    }else if(reduced.matches){ghosts=[];for(const b of bodies){b.x=b.tx;b.y=b.ty;b.life=1;}}
    draw();
  }
  show(root.children);requestAnimationFrame(tick);
  // Existing entry points open the same hierarchy, including validation prompts.
  document.querySelector('#style').onclick=()=>{
    function find(nodes,parents=[]){for(const node of nodes){if(node.id==='style'&&node.children)return [...parents,node];if(node.children){const found=find(node.children,[...parents,node]);if(found)return found;}}}
    const branch=find(root.children);
    if(branch){path=branch;show(path.at(-1).children,undefined,true);}else notify('Choose a style using the Style Presets cards.');
  };
  function setMenu(input){
    const next=validateMenu(typeof input==='string'?JSON.parse(input.replace(/^\uFEFF/,'')):input);
    root=next;path=[];elapsed=0;idleBlend=0;show(root.children);
  }
  window.GrooveLamp=Object.freeze({setMenu});
  const loadButton=document.createElement('button');loadButton.type='button';loadButton.textContent='Load menu JSON';
  const fileInput=document.createElement('input');fileInput.type='file';fileInput.accept='.json,application/json';fileInput.hidden=true;
  loadButton.onclick=()=>fileInput.click();
  fileInput.onchange=async()=>{
    const file=fileInput.files[0];if(!file)return;
    try{if(file.size>100000)throw Error('Menu files must be smaller than 100 KB.');setMenu(await file.text());notify('Menu loaded');}
    catch(error){notify('Menu unchanged: '+error.message);}
    finally{fileInput.value='';}
  };
  nav.append(loadButton,fileInput);
  document.querySelector('#see-all').addEventListener('click',()=>document.querySelector('#style').click());
  document.querySelector('#create').addEventListener('click',()=>{if(trackUrl&&!selected.style)document.querySelector('#style').click();});
})();
