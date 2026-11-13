'use strict';
function appendTeamName(cell,name,teams) {
  const found=(teams||[]).filter(t=>t.name.trim().toLocaleLowerCase('ru')===name.trim().toLocaleLowerCase('ru'));
  if(found.length===1 && found[0].logo_url){const img=document.createElement('img');img.className='broadcast-team-logo table-team-logo';img.alt='';img.src=found[0].logo_url;cell.append(img);}
  const label=document.createElement('span');label.textContent=name;cell.append(label);
}
function renderStandings(table, names, results, pointsPerWin, teams=[]) {
  const rows=names.map((name,i)=>({name,i,played:0,wins:0,points:0}));
  for(let i=0;i<5;i++) for(let j=i+1;j<5;j++) {
    const winner=results[i+'-'+j];
    if(winner!==i && winner!==j) continue;
    rows[i].played++; rows[j].played++; rows[winner].wins++;
  }
  rows.forEach(row=>row.points=row.wins*pointsPerWin);
  rows.sort((a,b)=>b.points-a.points || a.i-b.i);
  table.replaceChildren();
  const header=table.insertRow(); ['Место','Команда','Игры','Победы','Очки'].forEach(text=>header.insertCell().textContent=text);
  rows.forEach((row,index)=>{
    const place=index && rows[index-1].points===row.points ? rows[index-1].place : index+1;
    row.place=place; const tr=table.insertRow();
    tr.insertCell().textContent=place;appendTeamName(tr.insertCell(),row.name,teams);[row.played,row.wins,row.points].forEach(value=>tr.insertCell().textContent=value);
  });
}
