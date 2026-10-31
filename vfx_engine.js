/* HS-025: the studio.vfx/1 effect model, its seeded simulation and the Studio preview renderer.
 * Browser and Node-compatible. The simulation is analytic (positions are a closed-form function of
 * time), so scrubbing the timeline is exact and the same seed always gives the same trajectories.
 * studio_core/vfx.py mirrors the model, the validation and the simulation for the project core.
 * This is a Studio preview: nothing here claims how, or whether, Horizon renders an effect. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonVfx=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const SCHEMA='studio.vfx/1';
  const LIMITS={emitters:8,bursts:16,count:512,particles:2048,keys:16,duration:[0.05,10],speed:[0,60],lifetime:[0.01,10],
    gravity:[-50,50],drag:[0,20],spread:[0,180],radius:[0,10],stretch:[0,0.5],size:[0,8]};
  const ID=/^[a-z][a-z0-9_]{0,63}$/;
  const HEX=/^#[0-9a-f]{6}$/;
  const GOLDEN=0x9E3779B9;

  /** The Impact Spark preset: a hot burst of sparks with a short flash, for hits and breaking blocks. */
  function impactSpark(){
    return {schema:SCHEMA,name:'Impact Spark',duration:0.8,loop:false,seed:1337,emitters:[
      {id:'sparks',bursts:[{time:0,count:28}],shape:{type:'sphere',radius:0.12},direction:{axis:[0,1,0],spread:70},
        speed:[3.5,7],lifetime:[0.25,0.6],gravity:9.8,drag:2.5,stretch:0.035,blend:'additive',
        size:[[0,0.1],[0.7,0.06],[1,0]],color:[[0,'#fff6c8'],[0.35,'#ffbe3d'],[1,'#b8320f']],alpha:[[0,1],[0.8,0.9],[1,0]]},
      {id:'flash',bursts:[{time:0,count:1}],shape:{type:'point',radius:0},direction:{axis:[0,1,0],spread:0},
        speed:[0,0],lifetime:[0.09,0.09],gravity:0,drag:0,stretch:0,blend:'additive',
        size:[[0,0.45],[1,0.8]],color:[[0,'#ffffff'],[1,'#ffd36b']],alpha:[[0,0.95],[1,0]]},
    ]};
  }

  function mulberry32(seed){
    let a=seed>>>0;
    return function(){
      a=(a+0x6D2B79F5)>>>0;
      let t=Math.imul(a^a>>>15,a|1);
      t=(t+Math.imul(t^t>>>7,t|61))^t;
      return ((t^t>>>14)>>>0)/4294967296;
    };
  }

  const isNum=v=>typeof v==='number'&&Number.isFinite(v);

  /** Problems with an effect as [{path, code, message}]; empty when it can be simulated and saved. */
  function validate(effect){
    const out=[];
    const bad=(path,code,message)=>out.push({path,code,message});
    const range=(path,value,[lo,hi])=>{if(!isNum(value)||value<lo||value>hi)bad(path,'RANGE',`${path} must be a number from ${lo} to ${hi}`);};
    const pair=(path,value,limits)=>{
      if(!Array.isArray(value)||value.length!==2){bad(path,'PAIR',`${path} must be [min, max]`);return;}
      range(path+'[0]',value[0],limits);range(path+'[1]',value[1],limits);
      if(isNum(value[0])&&isNum(value[1])&&value[0]>value[1])bad(path,'ORDER',`${path}: min must not exceed max`);
    };
    const curve=(path,keys,check)=>{
      if(!Array.isArray(keys)||keys.length<2||keys.length>LIMITS.keys){bad(path,'CURVE',`${path} needs 2 to ${LIMITS.keys} keys`);return;}
      keys.forEach((key,i)=>{
        if(!Array.isArray(key)||key.length!==2||!isNum(key[0])){bad(`${path}[${i}]`,'KEY',`${path}[${i}] must be [time, value]`);return;}
        if(i>0&&isNum(keys[i-1]?.[0])&&key[0]<keys[i-1][0])bad(`${path}[${i}]`,'KEY_ORDER',`${path}: key times must not decrease`);
        check(`${path}[${i}]`,key[1]);
      });
      if(Array.isArray(keys[0])&&keys[0][0]!==0)bad(path,'KEY_START',`${path} must start at time 0`);
      if(Array.isArray(keys[keys.length-1])&&keys[keys.length-1][0]!==1)bad(path,'KEY_END',`${path} must end at time 1`);
    };
    if(!effect||typeof effect!=='object'){bad('','TYPE','An effect must be an object');return out;}
    if(effect.schema!==SCHEMA)bad('schema','SCHEMA',`schema must be ${SCHEMA}`);
    if(typeof effect.name!=='string'||!effect.name.trim()||effect.name.length>80)bad('name','NAME','name must be 1-80 characters');
    range('duration',effect.duration,LIMITS.duration);
    if(typeof effect.loop!=='boolean')bad('loop','TYPE','loop must be true or false');
    if(!Number.isInteger(effect.seed)||effect.seed<0||effect.seed>0xFFFFFFFF)bad('seed','SEED','seed must be an integer from 0 to 4294967295');
    const emitters=effect.emitters;
    if(!Array.isArray(emitters)||!emitters.length||emitters.length>LIMITS.emitters){
      bad('emitters','EMITTERS',`An effect needs 1 to ${LIMITS.emitters} emitters`);return out;
    }
    let total=0;const ids=new Set();
    emitters.forEach((e,i)=>{
      const p=`emitters[${i}]`;
      if(!e||typeof e!=='object'){bad(p,'TYPE',`${p} must be an object`);return;}
      if(typeof e.id!=='string'||!ID.test(e.id))bad(p+'.id','ID',`${p}.id: use lowercase letters, numbers and underscores`);
      else if(ids.has(e.id))bad(p+'.id','DUPLICATE',`Duplicate emitter id ${e.id}`);
      ids.add(e.id);
      if(!Array.isArray(e.bursts)||!e.bursts.length||e.bursts.length>LIMITS.bursts)bad(p+'.bursts','BURSTS',`${p} needs 1 to ${LIMITS.bursts} bursts`);
      else e.bursts.forEach((b,j)=>{
        range(`${p}.bursts[${j}].time`,b?.time,[0,LIMITS.duration[1]]);
        if(!Number.isInteger(b?.count)||b.count<1||b.count>LIMITS.count)bad(`${p}.bursts[${j}].count`,'COUNT',`count must be 1 to ${LIMITS.count}`);
        else total+=b.count;
      });
      if(!e.shape||!['point','sphere'].includes(e.shape.type))bad(p+'.shape','SHAPE','shape must be a point or a sphere');
      else range(p+'.shape.radius',e.shape.radius,LIMITS.radius);
      const axis=e.direction?.axis;
      if(!Array.isArray(axis)||axis.length!==3||!axis.every(isNum)||Math.hypot(...axis)<1e-6)bad(p+'.direction.axis','AXIS','axis must be a non-zero [x, y, z]');
      range(p+'.direction.spread',e.direction?.spread,LIMITS.spread);
      pair(p+'.speed',e.speed,LIMITS.speed);
      pair(p+'.lifetime',e.lifetime,LIMITS.lifetime);
      range(p+'.gravity',e.gravity,LIMITS.gravity);
      range(p+'.drag',e.drag,LIMITS.drag);
      range(p+'.stretch',e.stretch,LIMITS.stretch);
      if(!['additive','alpha'].includes(e.blend))bad(p+'.blend','BLEND','blend must be additive or alpha');
      curve(p+'.size',e.size,(path,v)=>range(path,v,LIMITS.size));
      curve(p+'.alpha',e.alpha,(path,v)=>range(path,v,[0,1]));
      curve(p+'.color',e.color,(path,v)=>{if(typeof v!=='string'||!HEX.test(v))bad(path,'COLOR',`${path} must be a colour like #ffbe3d`);});
    });
    if(total>LIMITS.particles)bad('emitters','BUDGET',`At most ${LIMITS.particles} particles per effect (${total} requested)`);
    return out;
  }

  function sample(keys,t){
    if(t<=keys[0][0])return keys[0][1];
    for(let i=1;i<keys.length;i++){
      const [t1,v1]=keys[i];
      if(t<=t1){const [t0,v0]=keys[i-1];const f=t1>t0?(t-t0)/(t1-t0):1;return v0+(v1-v0)*f;}
    }
    return keys[keys.length-1][1];
  }

  const rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));

  function gradient(keys,t){
    const channels=[0,1,2].map(c=>sample(keys.map(([k,v])=>[k,rgb(v)[c]]),t));
    return channels.map(v=>Math.round(v));
  }

  const norm=v=>{const l=Math.hypot(v[0],v[1],v[2]);return [v[0]/l,v[1]/l,v[2]/l];};
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];

  /** Spawn state of every particle: position, velocity, birth time and lifetime (depends on the seed only). */
  function spawn(effect){
    const particles=[];
    effect.emitters.forEach((e,index)=>{
      const random=mulberry32((effect.seed+index*GOLDEN)%4294967296);
      const axis=norm(e.direction.axis);
      const helper=Math.abs(axis[1])<0.99?[0,1,0]:[1,0,0];
      const b1=norm(cross(axis,helper)),b2=cross(b1,axis);
      const cosMax=Math.cos(e.direction.spread*Math.PI/180);
      for(const burst of e.bursts)for(let i=0;i<burst.count;i++){
        const u=[random(),random(),random(),random(),random(),random(),random()];
        const r=e.shape.type==='sphere'?e.shape.radius*Math.cbrt(u[0]):0;
        const cz=2*u[1]-1,sz=Math.sqrt(Math.max(0,1-cz*cz)),phi=2*Math.PI*u[2];
        const position=[r*sz*Math.cos(phi),r*cz,r*sz*Math.sin(phi)];
        const cosT=1-u[3]*(1-cosMax),sinT=Math.sqrt(Math.max(0,1-cosT*cosT)),psi=2*Math.PI*u[4];
        const local=[sinT*Math.cos(psi),cosT,sinT*Math.sin(psi)];
        const dir=[0,1,2].map(c=>b1[c]*local[0]+axis[c]*local[1]+b2[c]*local[2]);
        const speed=e.speed[0]+(e.speed[1]-e.speed[0])*u[5];
        const life=e.lifetime[0]+(e.lifetime[1]-e.lifetime[0])*u[6];
        particles.push({emitter:index,born:burst.time,life,position,velocity:dir.map(d=>d*speed)});
      }
    });
    return particles;
  }

  function positionAt(p,e,age){
    const g=[0,-e.gravity,0],k=e.drag;
    return [0,1,2].map(c=>k>1e-9
      ?p.position[c]+g[c]/k*age+(p.velocity[c]-g[c]/k)*(1-Math.exp(-k*age))/k
      :p.position[c]+p.velocity[c]*age+0.5*g[c]*age*age);
  }

  /** The particles alive at `time` seconds, with position, trail end, size, colour and opacity. */
  function simulate(effect,time,spawned=spawn(effect)){
    const t=effect.loop?((time%effect.duration)+effect.duration)%effect.duration:time;
    const alive=[];
    for(const p of spawned){
      const e=effect.emitters[p.emitter],age=t-p.born;
      if(age<0||age>=p.life)continue;
      const a=age/p.life;
      alive.push({emitter:p.emitter,age,position:positionAt(p,e,age),trail:positionAt(p,e,Math.max(0,age-e.stretch)),
        size:sample(e.size,a),alpha:sample(e.alpha,a),color:gradient(e.color,a),blend:e.blend});
    }
    return alive;
  }

  /** Draws one frame of the Studio preview on a 2D canvas (oblique view, metres to pixels). */
  function render(ctx,effect,time,{width=ctx.canvas.width,height=ctx.canvas.height,scale=height/2.6,spawned}={}){
    ctx.save();
    ctx.globalCompositeOperation='source-over';
    ctx.fillStyle='#0d1020';ctx.fillRect(0,0,width,height);
    const ox=width/2,oy=height*0.8;
    const project=([x,y,z])=>[ox+(x+z*0.35)*scale,oy-(y+z*0.2)*scale];
    ctx.fillStyle='#1f2747';
    for(let gx=-4;gx<=4;gx++){const [px]=project([gx*0.5,0,0]);ctx.fillRect(Math.round(px),Math.round(oy),1,1);}
    ctx.fillRect(0,Math.round(oy)+1,width,1);
    const particles=simulate(effect,time,spawned);
    for(const p of particles){
      ctx.globalCompositeOperation=p.blend==='additive'?'lighter':'source-over';
      const [r,g,b]=p.color;
      ctx.fillStyle=ctx.strokeStyle=`rgba(${r},${g},${b},${Math.max(0,Math.min(1,p.alpha)).toFixed(3)})`;
      const [hx,hy]=project(p.position),[tx,ty]=project(p.trail);
      const px=Math.max(1,Math.round(p.size*scale));
      if(Math.hypot(hx-tx,hy-ty)>=1){ctx.lineWidth=Math.max(1,Math.round(px/2));ctx.beginPath();ctx.moveTo(tx,ty);ctx.lineTo(hx,hy);ctx.stroke();}
      ctx.fillRect(Math.round(hx-px/2),Math.round(hy-px/2),px,px);
    }
    ctx.restore();
    return particles.length;
  }

  /** What the selected engine can do with this effect. `capabilities` is a profile's capability map. */
  function engineNotes(effect,capabilities){
    const caps=capabilities||{};
    const notes=[{level:'info',code:'STUDIO_PREVIEW',message:'Studio preview only: this is not how, or whether, Horizon renders it.'}];
    const custom=caps['render.custom_particles'];
    if(!custom||!usable(custom.status))notes.push({level:'warning',code:'NO_CUSTOM_PARTICLES',
      message:'Horizon has no contract for custom particles (render.custom_particles); the effect is kept in the project and not exported.'});
    const native=caps['native.particles'];
    const usable=status=>status==='official-static'||status==='engine-only';
    if(native&&usable(native.status))notes.push({level:'info',code:'NATIVE_PARTICLES',api:native.api,
      message:`Nearest engine feature: native.particles (${native.api??'?'}) queues vanilla particle types from authoritative server code; dust types carry two colours and a scale, but size curves, drag, trails and per-particle timing would be lost (HS-027).`});
    else notes.push({level:'info',code:'NO_NATIVE_PARTICLES',message:'This engine revision has no native.particles either.'});
    return notes;
  }

  return Object.freeze({SCHEMA,LIMITS,impactSpark,mulberry32,validate,spawn,simulate,render,engineNotes,sample,gradient});
});
