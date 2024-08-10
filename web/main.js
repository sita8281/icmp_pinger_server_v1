let timerId = null;
let api = '/api/hosts/all';

function callAjax(url, callback){
    var xmlhttp;
    // compatible with IE7+, Firefox, Chrome, Opera, Safari
    xmlhttp = new XMLHttpRequest();
    xmlhttp.onreadystatechange = function(){
        if (xmlhttp.readyState == 4 && xmlhttp.status == 200){
            callback(xmlhttp.responseText);
        }
    }
    xmlhttp.open("GET", url, true);
    xmlhttp.send();
}

function showHosts(data) {
    let json_data = JSON.parse(data);
    createTable(json_data);
    
}

function createTable(data_j) {
    let data = JSON.parse(data_j);
    let table_ = document.getElementById('table1');

    try {
        table_.remove();
    } catch (err) {
        null;
    }

    let div_content = document.getElementById('content');
    let table = document.createElement('table');
    table.id = 'table1';
    table.className = 'table';
    let thead = document.createElement('thead');
    let tr = document.createElement('tr');
    let th_status = document.createElement('th');
    th_status.textContent = 'Статус';
    th_status.id = 'status_col';
    let th_name = document.createElement('th');
    th_name.textContent = 'Название';
    th_name.id = 'name_col';
    let th_ip = document.createElement('th');
    th_ip.textContent = 'IP';
    let th_date = document.createElement('th');
    th_date.textContent = 'Время изменения';
    let tbody = document.createElement('tbody');

    tr.appendChild(th_status);
    tr.appendChild(th_name);
    tr.appendChild(th_ip);
    tr.appendChild(th_date);
    thead.appendChild(tr);
    table.appendChild(thead);

    for (let i=0; i < data.length; ++i) {
        var host = data[i];
        let img = null;

        if (host[3].search('clock') == 0) {
            img = 'images/clock.png';

        } else if (host[3].search('online') == 0) {
            img = 'images/icmp_good.png';

        } else if (host[3].search('offline') == 0) {
            img = 'images/icmp_bad.png';

        } else if (host[3].search('pause') == 0) {
            img = 'images/pause1.png';

        };

        let tr2 = document.createElement('tr');
        let img_html = document.createElement('img');
        img_html.src = img;
        let td_status = document.createElement('td');
        td_status.appendChild(img_html);
        let td_name = document.createElement('td');
        td_name.textContent = host[1];
        let td_ip = document.createElement('td');
        td_ip.textContent = host[0];
        let td_date = document.createElement('td');
        var date = getTimeString(host[4]);
        td_date.textContent = date;

        tr2.appendChild(td_status);
        tr2.appendChild(td_name);
        tr2.appendChild(td_ip);
        tr2.appendChild(td_date);

        tbody.appendChild(tr2);
        table.appendChild(tbody);
        div_content.appendChild(table);

        
    };
timerId = setTimeout(updateTable, 1000);

}

function updateTable() {
    console.log('111')
    if (api != null) {
        callAjax(api, createTable)
    };
};

function getTimeString (timestamp) {
    var a = new Date(timestamp * 1000);
    var month_ = String(Number(a.getMonth()) + 1)
    var month = ('00' + month_).slice(-2);
    var year = a.getFullYear();
    var day = ('00' + a.getDate()).slice(-2);
    var hour = ('00' + a.getHours()).slice(-2);
    var min = ('00' + a.getMinutes()).slice(-2);
    var sec = ('00' + a.getSeconds()).slice(-2);

    var t = day + '/' + month + '/' + year + '  ' + hour + ':' + min + ':' + sec
    return t;
}

document.getElementById('all_hosts').onclick = getAll;
document.getElementById('live_hosts').onclick = getLive;
document.getElementById('dead_hosts').onclick = getDead;
document.getElementById('pause_hosts').onclick = getPause;
document.getElementById('check_all').onclick = checkAll;
document.getElementById('check_dead').onclick = checkDead;

function getAll() {
    if (timerId != null) {
        clearTimeout(timerId);
    }
    api = '/api/hosts/all';
    callAjax(api, createTable);

};
function getDead() {
    if (timerId != null) {
        clearTimeout(timerId);
    }
    api = '/api/hosts/dead';
    callAjax(api, createTable);
};
function getLive() {
    if (timerId != null) {
        clearTimeout(timerId);
    }
    api = '/api/hosts/live';
    callAjax(api, createTable);
};
function getPause() {
    if (timerId != null) {
        clearTimeout(timerId);
    }
    api = '/api/hosts/pause';
    callAjax(api, createTable);
};
function checkAll() {
    callAjax('/api/check_all', function(){
        window.alert('Пинг хостов запущен');
    });
};
function checkDead() {
    callAjax('/api/check_dead', function(){
        window.alert('Пинг нерабочих хостов запущен');
    });
};



