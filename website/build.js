const fs=require('fs'); const path=require('path');
function cp(src,dst){const st=fs.statSync(src); if(st.isDirectory()){fs.mkdirSync(dst,{recursive:true}); for(const f of fs.readdirSync(src)) cp(path.join(src,f),path.join(dst,f));} else {fs.mkdirSync(path.dirname(dst),{recursive:true}); fs.copyFileSync(src,dst);}}
fs.rmSync('dist',{recursive:true,force:true}); fs.mkdirSync('dist',{recursive:true});
for (const f of ['index.html','app.js','data']) cp(f,path.join('dist',f));
for (const f of ['data/demo-leaderboard.json','data/demo-result.json']) JSON.parse(fs.readFileSync(f,'utf8'));
console.log('website built');
