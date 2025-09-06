pipeline {
    agent any

    environment {
        // Environment variables are securely managed in Jenkins
        // These will be retrieved from the Jenkins credentials store
        EPUB_READWISE_TOKEN = credentials('EPUB_READWISE_TOKEN')
        EPUB_FTP_PASS = credentials('EPUB_FTP_PASS')
        // Non-secret variables can be defined here
        GAS_ENDPOINT_EPUBS_PROCESSED_TRACKER = credentials('GAS_ENDPOINT_EPUBS_PROCESSED_TRACKER')
    }

    stages {
        stage('Setup Environment and Dependencies') {
            steps {
                script {
                    // Check for python3
                    try {
                        sh 'python3 --version'
                    } catch (e) {
                        error('Python 3 is not installed or not in the PATH. Please install it on the Jenkins agent.')
                    }

                    // Create and activate a virtual environment
                    sh 'python3 -m venv venv'
                    sh 'source venv/bin/activate'

                    // Install Python dependencies from requirements.txt
                    sh 'pip install -r requirements.txt'

                    // Add /usr/local/bin to the PATH for kepubify
                    sh 'export PATH="/usr/local/bin:$PATH"'
                }
            }
        }

        stage('Run Script') {
            steps {
                script {
                    // Run the main script
                    sh 'python3 readwise_to_epub/readwise_to_epub.py'
                }
            }
        }
    }
}