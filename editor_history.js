/* Bounded immutable editor snapshots. Browser and Node-compatible; no storage IO. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.HorizonStudioHistory=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  class Journal {
    constructor(limit=60,maxBytes=24*1024*1024){
      if(!Number.isInteger(limit)||limit<1||!Number.isInteger(maxBytes)||maxBytes<256)
        throw Error('Invalid history limits');
      this.limit=limit;this.maxBytes=maxBytes;
      this.before=[];this.after=[];this.current=null;
    }
    _encode(value){
      const string=JSON.stringify(value);
      if(typeof string!=='string')throw Error('History needs a JSON document');
      return string;
    }
    _parse(string){return JSON.parse(string);}
    reset(value){this.current=this._encode(value);this.before=[];this.after=[];}
    record(value){
      const next=this._encode(value);
      if(this.current===null){this.reset(value);return false;}
      if(this.current===next)return false;
      this.before.push(this.current);
      this.current=next;
      this.after=[];
      this._trim();
      return true;
    }
    _trim(){
      while(this.before.length>this.limit)this.before.shift();
      // Count string memory conservatively in UTF-16 bytes.
      while(this.before.length>0&&
        (this.before.reduce((sum,s)=>sum+s.length*2,0)+this.current.length*2>this.maxBytes))
        this.before.shift();
    }
    get canUndo(){return this.before.length>0;}
    get canRedo(){return this.after.length>0;}
    undo(){
      if(!this.canUndo)return null;
      this.after.push(this.current);
      this.current=this.before.pop();
      return this._parse(this.current);
    }
    redo(){
      if(!this.canRedo)return null;
      this.before.push(this.current);
      this.current=this.after.pop();
      this._trim();
      return this._parse(this.current);
    }
  }
  return {Journal};
});
