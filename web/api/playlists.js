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
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
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
                range: 'Playlists!A:C'
            });
            
            const rows = response.data.values;
            const playlists = rows.slice(1).map(row => ({
                id: row[0],
                name: row[1],
                videoIds: row[2] ? row[2].split(',') : []
            }));
            
            return res.status(200).json(playlists);
        }

        if (req.method === 'POST') {
            const { name } = req.body;
            
            const playlistsRes = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Playlists!A:A'
            });
            
            const newId = `pl${playlistsRes.data.values.length}`;
            
            await sheets.spreadsheets.values.append({
                spreadsheetId: SHEET_ID,
                range: 'Playlists!A:C',
                valueInputOption: 'RAW',
                resource: { values: [[newId, name, '']] }
            });
            
            return res.status(200).json({ success: true, id: newId });
        }

        if (req.method === 'PUT') {
            const { id } = req.query;
            const { name, videoIds } = req.body;
            
            const response = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Playlists!A:C'
            });
            
            const rows = response.data.values;
            const rowIndex = rows.findIndex(row => row[0] === id);
            
            if (rowIndex === -1) {
                return res.status(404).json({ error: 'Playlist not found' });
            }
            
            const newRow = [id, name, (videoIds || []).join(',')];
            
            await sheets.spreadsheets.values.update({
                spreadsheetId: SHEET_ID,
                range: `Playlists!A${rowIndex + 1}:C${rowIndex + 1}`,
                valueInputOption: 'RAW',
                resource: { values: [newRow] }
            });
            
            return res.status(200).json({ success: true });
        }

        if (req.method === 'DELETE') {
            const { id } = req.query;
            
            const response = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Playlists!A:C'
            });
            
            const rows = response.data.values;
            const rowIndex = rows.findIndex(row => row[0] === id);
            
            if (rowIndex === -1) {
                return res.status(404).json({ error: 'Playlist not found' });
            }
            
            await sheets.spreadsheets.batchUpdate({
                spreadsheetId: SHEET_ID,
                resource: {
                    requests: [{
                        deleteDimension: {
                            range: {
                                sheetId: 6,
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