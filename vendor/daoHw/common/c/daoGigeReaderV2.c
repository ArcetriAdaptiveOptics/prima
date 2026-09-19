#include <stdint.h>
#include <stdio.h>
#include <daoGigeReader.h>


// const char ip[] = "169.254.233.1";
// int port = 39433;


int main(int argc, char * argv[])
{
    if(argc != 7)
    {
        printf("Usage: %s <ip> <port> <filepath> <Width> <Height> <MTU>\n", argv[0]);
        return 1;
    }

    char *ip = argv[1];
    int port = atoi(argv[2]);
    char *filepath = argv[3];
    int width = atoi(argv[4]);
    int height = atoi(argv[5]);
    int mtu = atoi(argv[6]);

    printf("IP: %s\n", ip);
    printf("Port: %d\n", port);
    printf("Filepath: %s\n", filepath);
    printf("Width: %d\n", width);
    printf("Height: %d\n", height);
    printf("MTU: %d\n", mtu);
    // TODO make this a thread
    daoGigeReaderV2(ip, port, filepath, width, height, mtu);

    return 0;
}
