const { google } = require('googleapis');
const SCOPES = ['https://www.googleapis.com/auth/spreadsheets'];

async function getSheetsService() {
    const credentials = JSON.parse(process.env.GOOGLE_CREDENTIALS);
    const auth = new google.auth.GoogleAuth({
        credentials,
        scopes: SCOPES
    });
    return google.sheets({ version: 'v4', auth });
}

module.exports = async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    try {
        const sheets = await getSheetsService();
        const SHEET_ID = process.env.SHEET_ID;

        if (req.method === 'GET') {
            const response = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Categories!A:C'
            });
            
            const rows = response.data.values;
            const categories = rows.slice(1).map(row => ({
                id: row[0],
                name: row[1],
                short_name: row[2]
            }));
            
            return res.status(200).json(categories);
        }

        if (req.method === 'POST') {
            const { name, short_name } = req.body;
            
            const catsRes = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Categories!A:A'
            });
            
            const newId = String(catsRes.data.values.length);
            
            await sheets.spreadsheets.values.append({
                spreadsheetId: SHEET_ID,
                range: 'Categories!A:C',
                valueInputOption: 'RAW',
                resource: { values: [[newId, name, short_name]] }
            });
            
            return res.status(200).json({ success: true });
        }

        if (req.method === 'DELETE') {
            const { id } = req.query;
            
            const response = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Categories!A:C'
            });
            
            const rows = response.data.values;
            const rowIndex = rows.findIndex(row => row[0] === id);
            
            if (rowIndex === -1) {
                return res.status(404).json({ error: 'Category not found' });
            }
            
            await sheets.spreadsheets.batchUpdate({
                spreadsheetId: SHEET_ID,
                resource: {
                    requests: [{
                        deleteDimension: {
                            range: {
                                sheetId: 5,
                                dimension: 'ROWS',
                                startIndex: rowIndex,
                                endIndex: rowIndex + 1
                            }
                        }
                    }]
                }
            });
            
            return res.status(200).json({ success: true });
        }
        
        return res.status(405).json({ error: 'Method not allowed' });
    } catch (error) {
        console.error('Error:', error);
        return res.status(500).json({ error: error.message });
    }
};