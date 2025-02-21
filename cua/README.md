
This is a Python sample that uses the Computer Using Agent (CUA) model to control a computer.

This sample supports both a local computer or a remote machine served using VNC.

This pretty much works, although we're still working through some bugs in the vnc commands...

# Setup

## Setup the environment

1. Clone the repo
2. Run `pip install -r requirements.txt`
3. Set these follow environment variables:
    - If you are using OpenAI endpoint:
        ```env
        OPENAI_API_KEY="<YOUR_OPENAI_KEY>"
        ```
    - If you are using Azure OpenAI endpoint, first obtain the bearer token:
        ```bash
        az account get-access-token --scope https://cognitiveservices.azure.com/.default
        ```
        Then set the following environment variables:
        ```env
        AZURE_OPENAI_ENDPOINT="<YOUR_AZURE_OPENAI_ENDPOINT>" 
        AZURE_OPENAI_API_KEY="<YOUR_BEARER_TOKEN_OBTAINED_ABOVE>"
        ```

## Run with a local machine

Run `python app.py --endpoint azure --instructions "Find me a dishwasher safe pasta spoon on Amazon."`

## Run with a remote VNC machine

### Linux VM Creation in Windows

Note: this is most easily ran directly from windows, which avoids additional networking configs to get WSL talking to hyper-v

* [Enable Hyper-V on Windows](https://learn.microsoft.com/en-us/virtualization/hyper-v-on-windows/quick-start/enable-hyper-v#enable-hyper-v-using-powershell)
* Download the ISO for [Ubuntu 20.04.6 LTS (Focal Fossa)](https://releases.ubuntu.com/20.04.6/?_gl=1*1b7bnrl*_gcl_au*OTAyNTM1ODUzLjE3Mzc0MzYyMTg.&_ga=2.162259708.1981801007.1737436213-942790690.1737436213)
* Create a Hyper-V Ubuntu 20.04 LTS VM
  * Point it at the ISO you downloaded as its Boot DVD
* When the VM starts up, it will fail to boot.
  * Stop the VM. Go to the Settings for that VM, and turn off Secure Boot.
  * Now start the VM again and it will install Ubuntu Linux.
* In Hyper-V, go to **Actions->Hyper-V Settings** in the right sidebar. Go to **Enhanced Session Mode Policy**, and turn off **Allow enhanced session mode**. If you do not do this, mouse events may not be properly captured.

### Linux VM Setup

Once you've got the Linux VM installed, open a terminal.

* Install x11vnc

  ```
  sudo apt install x11vnc
  ```
* Find out what IP address the VM is using by running the following command:

  ```
  ip address | grep eth0
  ```
* Run the following command from the VM to start vnv server:

  ```
  x11vnc -forever -geometry 1024x768 -wait 50 -nopw -shared
  ```
* **Optional:** connect to the VM from hyper-v so you can watch the computer control model in action.

### How To Use The Script

1. Make sure your environment is set up as described above.
2. Make sure your VM is running and the VNC server is started.
3. Run `python app.py --vm-address=<YOUR_VM_IP_ADDRESS> --endpoint azure --autoenter --instructions "Find me a dishwasher safe silicone pasta spoon on Amazon."` using the IP address you gathered from your VM earlier.

Arguments

- `--vm-address` (str): The address of the VM to use. Default is "192.168.236.154".
- `--instructions`: Instructions to follow. If this is not specified, the script will ask you for the instructions when it starts up.
- `--alt-screen-size` (bool): Flag to enable alternative screen size. Default is False.
- `--model`: The model to use. Default is "computer-use-alpha".
- `--environment`: The environment to use. Default is "linux".
- `--autoenter` (bool): Flag to enable auto-enter functionality. If you do not enable this permission, it will prompt you to press Enter at every step. Default is False.
- `--endpoint` (string): The endpoint to use, either `azure` or `openai`. Default is `azure`.
