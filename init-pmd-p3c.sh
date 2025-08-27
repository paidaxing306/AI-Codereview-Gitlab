wget https://github.com/pmd/pmd/releases/download/pmd_releases%2F6.55.0/pmd-bin-6.55.0.zip plugin
unzip plugin/pmd-bin-6.55.0.zip
wget https://repo1.maven.org/maven2/com/alibaba/p3c/p3c-pmd/2.1.1/p3c-pmd-2.1.1.jar plugin
mv plugin/p3c-pmd-2.1.1.jar plugin/pmd-bin-6.55.0/lib
