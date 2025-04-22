import boto3
import os
import time
import requests  # Missing in your original code
from flask import Flask, request, redirect, jsonify
from werkzeug.utils import secure_filename

application = Flask(__name__)

# S3 Bucket Names
INPUT_BUCKET = 'my-audio-translation-bucket'
OUTPUT_BUCKET = 'speech-app-output-bucket'

# AWS clients
s3 = boto3.client('s3')
polly = boto3.client('polly')
transcribe = boto3.client('transcribe')

# File upload directory
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Set upload folder for Flask app
application.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Route for Text-to-Speech (TTS)
@application.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(application.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    s3.upload_file(filepath, INPUT_BUCKET, filename)

    with open(filepath, 'r') as f:
        text = f.read()

    response = polly.synthesize_speech(Text=text, OutputFormat='mp3', VoiceId='Joanna')
    audio_path = os.path.join(UPLOAD_FOLDER, 'output.mp3')

    with open(audio_path, 'wb') as audio_file:
        audio_file.write(response['AudioStream'].read())

    s3.upload_file(audio_path, OUTPUT_BUCKET, 'output.mp3')

    output_url = f"https://{OUTPUT_BUCKET}.s3.amazonaws.com/output.mp3"
    return redirect(output_url)


# Route for Speech-to-Text (STT)
@application.route('/speech-to-text', methods=['POST'])
def speech_to_text():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(application.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    s3.upload_file(filepath, INPUT_BUCKET, filename)

    file_ext = os.path.splitext(filename)[1].replace('.', '')
    media_format = file_ext.lower()

    s3_uri = f"s3://{INPUT_BUCKET}/{filename}"
    job_name = f"transcription-{filename}".replace(".", "-").replace(" ", "-")

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={'MediaFileUri': s3_uri},
        MediaFormat=media_format,
        LanguageCode='en-US'
    )

    while True:
        status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        job_status = status['TranscriptionJob']['TranscriptionJobStatus']

        if job_status == 'COMPLETED':
            transcript_uri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
            break
        elif job_status == 'FAILED':
            return jsonify({"error": "Transcription job failed"}), 500

        time.sleep(5)  # Wait before checking again

    transcript_response = requests.get(transcript_uri)
    transcript = transcript_response.json()['results']['transcripts'][0]['transcript']

    transcript_path = os.path.join(UPLOAD_FOLDER, 'transcript.txt')
    with open(transcript_path, 'w') as f:
        f.write(transcript)

    s3.upload_file(transcript_path, OUTPUT_BUCKET, 'transcript.txt')

    output_url = f"https://{OUTPUT_BUCKET}.s3.amazonaws.com/transcript.txt"
    return redirect(output_url)


if __name__ == '__main__':
    application.run(debug=True)
