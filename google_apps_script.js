/**
 * LAMÁ Beauty — Google Sheets order webhook
 *
 * Setup:
 * 1. Open your Google Sheet (Orders lama store)
 * 2. Extensions → Apps Script → paste this file → Save
 * 3. Deploy → New deployment → Web app
 *    - Execute as: Me
 *    - Who has access: Anyone
 * 4. Copy the deployment URL into backend GOOGLE_SHEETS_WEBHOOK_URL
 *
 * Set Script Property WEBHOOK_SECRET to the same value as
 * GOOGLE_SHEETS_WEBHOOK_SECRET. Orders are upserted by ORDER ID.
 */

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse({ success: false, error: 'Missing JSON body' });
    }
    var data = JSON.parse(e.postData.contents);
    var expectedSecret = PropertiesService.getScriptProperties().getProperty('WEBHOOK_SECRET');
    if (!expectedSecret || data.secret !== expectedSecret) {
      return jsonResponse({ success: false, error: 'Unauthorized' });
    }

    lock.waitLock(30000);
    var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = spreadsheet.getSheetByName('Orders') || spreadsheet.insertSheet('Orders');
    var headers = [
      'DATE', 'ORDER ID', 'COUNTRY', 'NAME', 'PHONE', 'CITY', 'PRODUCT',
      'SKU', 'QUANTITY', 'SUBTOTAL', 'SHIPPING', 'TOTAL PRICE', 'CURRENCY',
      'STATUS', 'SOURCE', 'UPSELL'
    ];
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

    var row = [
      safeCell(data.date || ''),
      safeCell(data.orderId || ''),
      safeCell(data.country || 'KSA'),
      safeCell(data.name || ''),
      safeCell(data.phone || ''),
      safeCell(data.city || ''),
      safeCell(data.product || ''),
      safeCell(data.sku || ''),
      safeCell(data.quantity || ''),
      data.subtotal != null ? data.subtotal : '',
      data.shipping != null ? data.shipping : '',
      data.totalPrice != null ? data.totalPrice : '',
      safeCell(data.currency || 'SAR'),
      safeCell(data.status != null ? data.status : ''),
      safeCell(data.source || 'website'),
      safeCell(data.upsell || '')
    ];

    if (!data.orderId) {
      return jsonResponse({ success: false, error: 'Missing orderId' });
    }
    var targetRow = sheet.getLastRow() + 1;
    if (sheet.getLastRow() > 1) {
      var ids = sheet.getRange(2, 2, sheet.getLastRow() - 1, 1).getValues();
      for (var i = 0; i < ids.length; i++) {
        if (String(ids[i][0]) === String(data.orderId)) {
          targetRow = i + 2;
          break;
        }
      }
    }
    sheet.getRange(targetRow, 1, 1, row.length).setValues([row]);
    SpreadsheetApp.flush();

    return jsonResponse({ success: true, orderId: data.orderId, row: targetRow });
  } catch (error) {
    return jsonResponse({ success: false, error: error.message });
  } finally {
    if (lock.hasLock()) {
      lock.releaseLock();
    }
  }
}

function doGet(e) {
  return jsonResponse({ status: 'LAMA Google Sheets webhook is active.' });
}

function safeCell(value) {
  var text = String(value == null ? '' : value);
  return /^[=+\-@]/.test(text) ? "'" + text : text;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
