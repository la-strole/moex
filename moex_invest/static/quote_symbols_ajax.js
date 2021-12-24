// result = {NAME: [<russian_title>, <value>]}
var result = {};

function ajax_request(){
  
  /* Get value from symbol input field */
  let symbol = document.getElementById("symbol-input").value;
  
  /* Delete existing options */
  if (document.getElementById("symbols")){
    document.getElementById("symbols").remove();
  }
    
  if (symbol){

    var aj = new XMLHttpRequest();
    
    /* Сallback function */
    aj.onreadystatechange = function(){

      if (aj.readyState == 4 && aj.status == 200){

        /* 1. Сreate datalist node */
        let parent = document.createElement("datalist");
        parent.id = "symbols";
        document.getElementById("symbol-input").appendChild(parent);

        /* 2. Get json as list of 10 symbols from server */
        let possible_symbols = JSON.parse(aj.responseText);

        /* 3. Add options tags to input */
        for (let s of possible_symbols){
          /* Create new node */
          let node = document.createElement("option");
          /* Set node value to value from json response */
          node.value = s;
          /* Put element to document */
          document.getElementById("symbols").appendChild(node);
        }
      };
    };
    aj.open("GET", `/sandbox/quote?q=${symbol}`, true);
    aj.send();
  }
}

function ajax_get_primary_board(){

  // 1. Clear result - object with market data from moex api server
  result = {}

  // 2. Clear detail info 
  if (document.getElementById("parent_add_detail_info")){
    document.getElementById("parent_add_detail_info").remove();
  }
  // Clear ticker alert div
  remove_ticker_alert();
  
  document.getElementById('market_price').innerHTML = "N/A";
  document.getElementById('bid').innerHTML = "N/A";
  document.getElementById('offer').innerHTML = "N/A";
  document.getElementById('lot').innerHTML = "N/A";

  // 3. Make Buy button disable until offers exist 
  if (!document.getElementById("button_buy").classList.contains('disabled')){
    document.getElementById("button_buy").classList.add("disabled");
  }

  // 4. Get value from ticker input field
  let text = document.getElementById("symbol-input").value;
  let symbol = text.split(' ')[0];
       
  if (symbol){

    var aj = new XMLHttpRequest();
    
    /* Callback function */
    aj.onreadystatechange = function(){

      if (aj.readyState == 4 && aj.status == 200){
        
        /* Get json from moex api server */
        let primary_data = JSON.parse(aj.responseText);
        
        if (primary_data){

          /* Get columns number in description table */
          let name_index = primary_data["description"]["columns"].indexOf("name");
          let title_index = primary_data["description"]["columns"].indexOf("title");
          let value_index = primary_data["description"]["columns"].indexOf("value");

          /* Append data to result object */
          const not_interest = ["GROUP", "TYPE", "GROUPNAME", "EMITTER_ID"];
          for (let row of primary_data["description"]["data"]){
            if (!not_interest.includes(row[name_index])){
              result[row[name_index]] = [row[title_index], row[value_index]];
            }
          }
          
          /* Get data for furure price request */
          title_index = primary_data["boards"]["columns"].indexOf("title");
          let market_index = primary_data["boards"]["columns"].indexOf("market");
          let engine_index = primary_data["boards"]["columns"].indexOf("engine");
          let is_primary_index = primary_data["boards"]["columns"].indexOf("is_primary");
          let boardid_index = primary_data["boards"]["columns"].indexOf("boardid");
          let currencyid_index = primary_data["boards"]["columns"].indexOf("currencyid");
          

          for (row of primary_data["boards"]["data"]){

            /* Looking for primary trade board */
            if (row[is_primary_index] == 1){  
              var market = row[market_index];
              var engine = row[engine_index];
              var boardid = row[boardid_index];
              result['PRIME_BOARD'] = [["Основной режим торгов"], row[title_index]];
              result["CURRENCY_ID"] = [["Основная валюта"], row[currencyid_index]];
              break;
            }
          }

          /* New AJAX request to get current market price with engine, market, boardid. Add info to result{}*/
          if (engine && market && boardid && symbol){
            ajax_get_market_price(engine, market, boardid, symbol);
          }
          else {
            create_ticker_alert('Извините, не удалось получить информацию по вашему тикеру. Попробуйте другой.');
          }
        }
      }
    };
    aj.open("GET", `https://iss.moex.com/iss/securities/${symbol}.json?iss.meta=off&description.columns=name,title,value&boards.columns=secid,boardid,title,market,engine,is_primary,currencyid`, true);
    aj.send();
  }

  else console.log(`Error: ajax_get_primary_board: there is not symbol`);
}


function ajax_get_market_price(engine, market, boardid, symbol){

  /* Get current price from moex with API and change result object */
  var aj_1 = new XMLHttpRequest();
  
  /* Callback function */
  aj_1.onreadystatechange = function(){

    if (aj_1.readyState == 4 && aj_1.status == 200){
      
      /* Get json from moex api server */
      let price_data = JSON.parse(aj_1.responseText);
      
      /* Get lotsize */
      let lot_size_index = price_data["securities"]["columns"].indexOf("LOTSIZE");
      let addmited_price_index = price_data["securities"]["columns"].indexOf("PREVADMITTEDQUOTE");

      result['LOTSIZE'] = [["Размер лота"], price_data["securities"]["data"][0][lot_size_index]];
      result['PREVADMITTEDQUOTE'] = [["Котировка"], price_data["securities"]["data"][0][addmited_price_index]];
      
      /* Get current prices */
      let bid_index = price_data["marketdata"]["columns"].indexOf("BID");
      let offer_index = price_data["marketdata"]["columns"].indexOf("OFFER");
      let spread_index = price_data["marketdata"]["columns"].indexOf("SPREAD");
      let voltoday_index = price_data["marketdata"]["columns"].indexOf("VOLTODAY");

      result['BID'] = [["Спрос"], price_data["marketdata"]["data"][0][bid_index]];
      result['OFFER'] = [["Предложение"], price_data["marketdata"]["data"][0][offer_index]];
      result['SPRED'] = [["Спред"], price_data["marketdata"]["data"][0][spread_index]];
      result['VOLTODAY'] = [["Объем продаж последний"], price_data["marketdata"]["data"][0][voltoday_index]];
      
      // Change detail info html block
      change_detail_info(symbol, market);
    }
  }
  aj_1.open("GET", `https://iss.moex.com/iss/engines/${engine}/markets/${market}/boards/${boardid}/securities/${symbol}.json?iss.meta=off&iss.only=securities,marketdata&securities.columns=LOTSIZE,STATUS,PREVADMITTEDQUOTE&marketdata.columns=BID,OFFER,SPREAD,VOLTODAY`, true);
  aj_1.send();
}

function change_detail_info(symbol, market){

  if (result){
    
    /* Bonds price is % from base price, other - RUB or $ or EUR utf8 symbol */
    var symbol_val = '';
    if (result["CURRENCY_ID"][1] == 'USD'){
      symbol_val = '$';
    }
    else if (result["CURRENCY_ID"][1] == 'EUR'){
      symbol_val = '\u20AC';
    }
    else if (result["CURRENCY_ID"][1] == 'RUB' || result["CURRENCY_ID"][1] == 'SUR'){
      symbol_val = '\u20BD';
    }
    
    if (market == "bonds"){
      symbol_val = '%';
    }

    // Change visible detail info (\u00A0 - space)
    document.getElementById('market_price').innerHTML = result['PREVADMITTEDQUOTE'][1] + '\u00A0' + symbol_val;
    document.getElementById('lot').innerHTML = result['LOTSIZE'][1] + '\u00A0' + 'ед';
    if (result["BID"][1]){
      document.getElementById('bid').innerHTML = result['BID'][1];
    }
    else{
      document.getElementById('bid').innerHTML = "Нет спроса";
    }
    if (result["OFFER"][1]){
      document.getElementById('offer').innerHTML = result['OFFER'][1];
    }
    else{
      document.getElementById('offer').innerHTML = "Нет предложения";
    }
    

    /* If BID exist make buy button enable */

    if (result['OFFER'][1] != null){
      if (document.getElementById("button_buy").classList.contains('disabled')){
        document.getElementById("button_buy").classList.remove('disabled');
      }
    }
    
    /* Change info in more inform block (under button) */

    let parent = document.createElement("tbody");
    parent.id = "parent_add_detail_info";
    document.getElementById("parent_table").appendChild(parent);

    var tbody_detail = document.getElementById("parent_add_detail_info");

    for (const [key, value] of Object.entries(result)){

      var table_row = document.createElement("tr");
      var row_head = document.createElement("th");
      row_head.innerHTML = value[0];
      var row_data = document.createElement("th");
      row_data.innerHTML = value[1];
      table_row.appendChild(row_head);
      table_row.appendChild(row_data);
      tbody_detail.appendChild(table_row);
      
    }
  }
}

/* Check if DOM is full loaded - else - can not find elemnt id = symbols */
/* Check if DOM full loaded */

if (document.readyState === 'loading') {  // document still loaded

  console.log("DOM still loading - waiting...");

  document.addEventListener('DOMContentLoaded', function(){
    document.getElementById("symbol-input").addEventListener('input', ajax_request);
    document.getElementById("check_button").addEventListener('click', ajax_get_primary_board);});  
}
else {  // `DOMContentLoaded` is full loaded
  console.log("Try to add event listener to options block");
  document.getElementById("symbol-input").addEventListener('input',ajax_request);
  document.getElementById("check_button").addEventListener('click', ajax_get_primary_board);
}

function create_ticker_alert(message){
  
  // Create alert div
  let element = document.createElement('div');
  element.id = "alert_div";
  element.classList.add('alert');
  element.classList.add('alert-primary');
  element.setAttribute('role', 'alert');
  element.innerHTML = message;
  document.getElementById("ticker_alert_parrent").appendChild(element);
}

function remove_ticker_alert(){
  
  if (document.getElementById('alert_div')){
    document.getElementById('alert_div').remove();
  }
}