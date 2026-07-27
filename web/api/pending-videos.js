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
                range: 'PendingVideos!A:I'
            });
            
            const rows = response.data.values;
            const videos = rows.slice(1).map(row => ({
                id: row[0],
                title: row[1],
                channel_id: row[2],
                channel_name: row[3],
                published_at: row[4],
                duration: row[5],
                thumbnail_url: row[6],
                video_url: row[7],
                added_at: row[8]
            }));
            
            return res.status(200).json(videos);
        }

        if (req.method === 'POST') {
            const { id, category, members } = req.body;
            
            const pendingRes = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'PendingVideos!A:I'
            });
            
            const pendingRows = pendingRes.data.values;
            const pendingIndex = pendingRows.findIndex(row => row[0] === id);
            
            if (pendingIndex === -1) {
                return res.status(404).json({ error: 'Video not found' });
            }
            
            const pending = pendingRows[pendingIndex];
            
            const videoRow = [
                id, pending[1], pending[7], '', '',
                category || 'Interview', (members || []).join(','),
                pending[4] ? pending[4].split('T')[0] : '',
                pending[5] || '0:00',
                'false', 'false', 'false',
                pending[2], 'app'
            ];
            
            await sheets.spreadsheets.values.append({
                spreadsheetId: SHEET_ID,
                range: 'Videos!A:N',
                valueInputOption: 'RAW',
                resource: { values: [videoRow] }
            });
            
            await sheets.spreadsheets.batchUpdate({
                spreadsheetId: SHEET_ID,
                resource: {
                    requests: [{
                        deleteDimension: {
                            range: {
                                sheetId: 3,
                                dimension: 'ROWS',
                                startIndex: pendingIndex,
                                endIndex: pendingIndex + 1
                            }
                        }
                    }]
                }
            });
            
            return res.status(200).json({ success: true });
        }

        if (req.method === 'DELETE') {
            const { id } = req.query;
            
            const response = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'PendingVideos!A:I'
            });
            
            const rows = response.data.values;
            const rowIndex = rows.findIndex(row => row[0] === id);
            
            if (rowIndex === -1) {
                return res.status(404).json({ error: 'Video not found' });
            }
            
            await sheets.spreadsheets.batchUpdate({
                spreadsheetId: SHEET_ID,
                resource: {
                    requests: [{
                        deleteDimension: {
                            range: {
                                sheetId: 3,
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