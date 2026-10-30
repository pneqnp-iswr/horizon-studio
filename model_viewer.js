/* Horizon Studio Model Viewport: dependency-free WebGL, authored from scratch.
 * Supports vanilla cuboid "elements" and cube_all previews. No game assets included.
 */
(function () {
  'use strict';
  const vs = `attribute vec3 aPosition; attribute vec3 aNormal; attribute vec2 aUV;
    uniform mat4 uMatrix; varying vec3 vNormal; varying vec2 vUV;
    void main(){gl_Position=uMatrix*vec4(aPosition,1.);vNormal=aNormal;vUV=aUV;}`;
  const fs = `precision mediump float; varying vec3 vNormal; varying vec2 vUV;
    uniform sampler2D uTexture;
    void main(){vec3 light=normalize(vec3(.4,.9,.8));float diffuse=max(dot(normalize(vNormal),light),0.);
    vec3 tex=texture2D(uTexture,vUV).rgb;gl_FragColor=vec4(tex*(.48+.52*diffuse),1.);}`;
  const identity=()=>[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  function multiply(a,b){const c=Array(16).fill(0);for(let col=0;col<4;col++)for(let row=0;row<4;row++)for(let k=0;k<4;k++)c[col*4+row]+=a[k*4+row]*b[col*4+k];return c;}
  function rotateX(t){const c=Math.cos(t),s=Math.sin(t);return [1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1];}
  function rotateY(t){const c=Math.cos(t),s=Math.sin(t);return [c,0,-s,0,0,1,0,0,s,0,c,0,0,0,0,1];}
  function perspective(fovy,aspect,near,far){const f=1/Math.tan(fovy/2),nf=1/(near-far);return [f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0];}
  function translate(x,y,z){const m=identity();m[12]=x;m[13]=y;m[14]=z;return m;}
  function shader(gl,type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;}
  function program(gl){const p=gl.createProgram();gl.attachShader(p,shader(gl,gl.VERTEX_SHADER,vs));gl.attachShader(p,shader(gl,gl.FRAGMENT_SHADER,fs));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));return p;}
  function buildMesh(model){
    const elements=(model&&Array.isArray(model.elements)&&model.elements.length)?model.elements:[{from:[0,0,0],to:[16,16,16]}];
    if(elements.length>128)throw Error('128 element preview limit');
    const points=[],normals=[],uvs=[];
    const faces=[
      {name:'north',n:[0,0,-1],p:[[0,0,0],[1,0,0],[1,1,0],[0,1,0]]},
      {name:'south',n:[0,0,1],p:[[1,0,1],[0,0,1],[0,1,1],[1,1,1]]},
      {name:'east',n:[1,0,0],p:[[1,0,0],[1,0,1],[1,1,1],[1,1,0]]},
      {name:'west',n:[-1,0,0],p:[[0,0,1],[0,0,0],[0,1,0],[0,1,1]]},
      {name:'up',n:[0,1,0],p:[[0,1,0],[1,1,0],[1,1,1],[0,1,1]]},
      {name:'down',n:[0,-1,0],p:[[0,0,1],[1,0,1],[1,0,0],[0,0,0]]},
    ];
    for(const el of elements){
      if(!el||!Array.isArray(el.from)||!Array.isArray(el.to)||el.from.length!==3||el.to.length!==3)throw Error('Invalid cuboid coordinates');
      const min=el.from.map(x=>Number(x)/16-.5), max=el.to.map(x=>Number(x)/16-.5);
      if([...min,...max].some(x=>!Number.isFinite(x)))throw Error('Non-finite cuboid coordinates');
      for(const face of faces){
        if(el.faces&&el.faces[face.name]===undefined)continue;
        const polygon=face.p.map(([x,y,z])=>[min[0]+(max[0]-min[0])*x,min[1]+(max[1]-min[1])*y,min[2]+(max[2]-min[2])*z]);
        const coords=[[0,1],[1,1],[1,0],[0,0]];
        const uv=el.faces?.[face.name]?.uv;
        const corners=Array.isArray(uv)&&uv.length===4?[[uv[0]/16,1-uv[3]/16],[uv[2]/16,1-uv[3]/16],[uv[2]/16,1-uv[1]/16],[uv[0]/16,1-uv[1]/16]]:coords;
        for(const i of [0,1,2,0,2,3]){points.push(...polygon[i]);normals.push(...face.n);uvs.push(...corners[i]);}
      }
    }
    return {points:new Float32Array(points),normals:new Float32Array(normals),uvs:new Float32Array(uvs),triangles:points.length/3};
  }
  class Viewer {
    constructor(canvas){
      this.canvas=canvas;this.gl=canvas.getContext('webgl',{antialias:true,alpha:false});
      this.mesh=buildMesh({});this.yaw=.65;this.pitch=-.4;this.distance=3.0;this.active=true;this.image=null;
      const gl=this.gl;
      if(gl){this.p=program(gl);this.buffers={};for(const attr of ['points','normals','uvs'])this.buffers[attr]=gl.createBuffer();this.texture=gl.createTexture();this.createFallbackTexture();}
      else this.ctx=canvas.getContext('2d');
      this.setModel({});
      let dragging=false,oldX=0,oldY=0;
      canvas.addEventListener('pointerdown',e=>{dragging=true;oldX=e.clientX;oldY=e.clientY;canvas.setPointerCapture(e.pointerId);});
      canvas.addEventListener('pointerup',()=>{dragging=false;});
      canvas.addEventListener('pointercancel',()=>{dragging=false;});
      canvas.addEventListener('pointermove',e=>{if(!dragging)return;this.yaw+=(e.clientX-oldX)*.009;this.pitch=Math.max(-1.45,Math.min(1.45,this.pitch+(e.clientY-oldY)*.009));oldX=e.clientX;oldY=e.clientY;this.render();});
      canvas.addEventListener('wheel',e=>{e.preventDefault();this.distance=Math.min(8,Math.max(1.35,this.distance+e.deltaY*.004));this.render();},{passive:false});
      window.addEventListener('resize',()=>this.render());
    }
    createFallbackTexture(){
      const gl=this.gl;if(!gl)return;const pixels=new Uint8Array(16*16*4);
      for(let y=0;y<16;y++)for(let x=0;x<16;x++){const i=(y*16+x)*4,v=(Math.floor(x/4)+Math.floor(y/4))%2;pixels.set(v?[73,131,158,255]:[46,83,107,255],i);}
      gl.bindTexture(gl.TEXTURE_2D,this.texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,16,16,0,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    }
    setTexture(data){
      if(!data){this.image=null;this.createFallbackTexture();this.render();return;}
      if(!/^data:image\/png;base64,/.test(data))throw Error('Only local PNG textures are accepted');
      const image=new Image();image.onload=()=>{this.image=image;const gl=this.gl;if(gl){gl.bindTexture(gl.TEXTURE_2D,this.texture);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,1);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);}this.render();};
      image.onerror=()=>this.createFallbackTexture();image.src=data;
    }
    setModel(model){this.mesh=buildMesh(model);const gl=this.gl;if(gl)for(const [name,values] of Object.entries({points:this.mesh.points,normals:this.mesh.normals,uvs:this.mesh.uvs})){gl.bindBuffer(gl.ARRAY_BUFFER,this.buffers[name]);gl.bufferData(gl.ARRAY_BUFFER,values,gl.STATIC_DRAW);}this.render();}
    render(){
      const c=this.canvas,gl=this.gl;if(!this.active)return;if(!gl)return this.renderSoftware();
      const width=Math.max(1,Math.round(c.clientWidth*(window.devicePixelRatio||1))),height=Math.max(1,Math.round(c.clientHeight*(window.devicePixelRatio||1)));
      if(c.width!==width||c.height!==height){c.width=width;c.height=height;}
      gl.viewport(0,0,width,height);gl.clearColor(.03,.055,.085,1);gl.enable(gl.DEPTH_TEST);gl.enable(gl.CULL_FACE);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(this.p);
      const world=multiply(translate(0,0,-this.distance),multiply(rotateX(this.pitch),rotateY(this.yaw)));
      const matrix=multiply(perspective(Math.PI/3,width/height,.1,100),world);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.p,'uMatrix'),false,new Float32Array(matrix));
      for(const [name,attribute,size] of [['points','aPosition',3],['normals','aNormal',3],['uvs','aUV',2]]){const loc=gl.getAttribLocation(this.p,attribute);gl.bindBuffer(gl.ARRAY_BUFFER,this.buffers[name]);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,0,0);}
      gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,this.texture);gl.uniform1i(gl.getUniformLocation(this.p,'uTexture'),0);
      gl.drawArrays(gl.TRIANGLES,0,this.mesh.triangles);
    }
    renderSoftware(){
      const canvas=this.canvas,ctx=this.ctx;if(!ctx)return;
      const w=Math.max(1,canvas.clientWidth),h=Math.max(1,canvas.clientHeight);canvas.width=Math.round(w);canvas.height=Math.round(h);
      ctx.fillStyle='#0d1820';ctx.fillRect(0,0,w,h);
      const faces=[];const p=this.mesh.points,n=this.mesh.normals;
      const rotated=(x,y,z)=>{
        const c=Math.cos(this.yaw),s=Math.sin(this.yaw),cx=Math.cos(this.pitch),sx=Math.sin(this.pitch);
        const a=x*c+z*s,b=-x*s+z*c;return [a,y*cx-b*sx,y*sx+b*cx];
      };
      const size=Math.min(w,h)*.85/this.distance;
      for(let i=0;i<p.length;i+=18){
        const vertices=[];let depth=0;
        for(const t of [0,1,2,5]){
          const point=rotated(p[i+t*3],p[i+t*3+1],p[i+t*3+2]);depth+=point[2];
          const f=size/(1+point[2]*.18);vertices.push([w/2+point[0]*f,h/2-point[1]*f]);
        }
        const faceNormal=rotated(n[i],n[i+1],n[i+2]);
        const shade=.5+.5*Math.max(0,faceNormal[0]*.38+faceNormal[1]*.8+faceNormal[2]*.4);
        faces.push({vertices,depth:depth/4,shade});
      }
      faces.sort((a,b)=>b.depth-a.depth);
      for(const face of faces){ctx.beginPath();ctx.moveTo(...face.vertices[0]);for(const point of face.vertices.slice(1))ctx.lineTo(...point);ctx.closePath();
        const v=Math.round(150*face.shade);ctx.fillStyle=`rgb(${Math.round(v*.55)},${Math.round(v*.92)},${v})`;ctx.fill();ctx.lineWidth=.7;ctx.strokeStyle='#101820';ctx.stroke();}
      ctx.fillStyle='#bac9d0';ctx.font='12px monospace';ctx.fillText('3D geometry · software preview',12,22);
    }
  }
  window.HorizonModelViewer={Viewer,buildMesh};
})();
