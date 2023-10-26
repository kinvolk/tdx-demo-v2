# Azure TDX demo

This demo depicts how a confidential job is running on a TDX TEE via Cloud API Adaptor.

## Install Cloud API Adaptor

Adapted from the [instructions to deploy Cloud API Adaptor on
Azure](https://github.com/confidential-containers/cloud-api-adaptor/blob/4f2375bdbe116a6dd3724010c6325b4d27e1d0a7/azure/README.md).

### Initial setup

Retrieve your subscription ID and set the region

```bash
export AZURE_SUBSCRIPTION_ID=$(az account show --query id --output tsv)
export AZURE_REGION="eastus2"
```

**Important: use region "eastus2", TDX CVMs might not be available in other regions**

Create resource group

```bash
export AZURE_RESOURCE_GROUP="caa-rg-$(date '+%Y%M%d%H%M')"

az group create \
  --name "${AZURE_RESOURCE_GROUP}" \
  --location "${AZURE_REGION}"
```

Create demo directory:

```bash
mkdir demo
export BASEDIR="$PWD/demo"
```

Clone and checkout the relevant commits of the different projects involved

```bash
cd $BASEDIR

git clone https://github.com/iaguis/guest-components -b iaguis/add-az-tdx-vtpm-attester
cd guest-components && git checkout 5678e4100fdab2fc6ceacca7686cb22237a82db6 && cd -

git clone https://github.com/mkulke/attestation-service -b mkulke/add-az-tdx-vtpm-verifier
cd attestation-service && git checkout 8f90383fd1febd285eb1c3dfed721c67757137b4 && cd -

git clone https://github.com/kata-containers/kata-containers -b CCv0
cd kata-containers && git checkout 135c166b8ee9cb8f966df97fd9690424a96dc264 && cd -

git clone https://github.com/confidential-containers/cloud-api-adaptor
cd cloud-api-adaptor && git checkout 4f2375bdbe116a6dd3724010c6325b4d27e1d0a7 && cd -
```

### Build PodVM image

Create shared image gallery

```bash
export GALLERY_NAME="caaubnttdxcvmsGallery"
az sig create \
  --gallery-name "${GALLERY_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --location "${AZURE_REGION}"
```

Create image definition

```bash
export GALLERY_IMAGE_DEF_NAME="cc-image"
az sig image-definition create \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --gallery-name "${GALLERY_NAME}" \
  --gallery-image-definition "${GALLERY_IMAGE_DEF_NAME}" \
  --publisher GreatPublisher \
  --offer GreatOffer \
  --sku GreatSku \
  --os-type "Linux" \
  --os-state "Generalized" \
  --hyper-v-generation "V2" \
  --location "${AZURE_REGION}" \
  --architecture "x64" \
  --features SecurityType=ConfidentialVmSupported
```

Change directory to the CAA image builder

```
cd $BASEDIR/cloud-api-adaptor/azure/image
```

Build PodVM image

```bash
export PKR_VAR_resource_group="${AZURE_RESOURCE_GROUP}"
export PKR_VAR_location="${AZURE_REGION}"
export PKR_VAR_subscription_id="${AZURE_SUBSCRIPTION_ID}"
export PKR_VAR_use_azure_cli_auth=true
export PKR_VAR_az_gallery_name="${GALLERY_NAME}"
export PKR_VAR_az_gallery_image_name="${GALLERY_IMAGE_DEF_NAME}"
export PKR_VAR_az_gallery_image_version="0.0.1"
export PKR_VAR_offer=0001-com-ubuntu-confidential-vm-jammy
export PKR_VAR_sku=22_04-lts-cvm

export AA_KBC="cc_kbc_az_tdx_vtpm"
export CLOUD_PROVIDER=azure
export LIBC="gnu"
PODVM_DISTRO=ubuntu make image
```

Use the output of the `ManagedImageSharedImageGalleryId` field to set Image ID env variable:

```bash
# e.g. format: /subscriptions/.../resourceGroups/.../providers/Microsoft.Compute/galleries/.../images/.../versions/../
export AZURE_IMAGE_ID="/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}/providers/Microsoft.Compute/galleries/${GALLERY_NAME}/images/${GALLERY_IMAGE_DEF_NAME}/versions/${PKR_VAR_az_gallery_image_version}"
```

### Deploy Kubernetes with AKS

```bash
export CLUSTER_NAME="caa-$(date '+%Y%M%d%H%M')"
export AKS_WORKER_USER_NAME="azuser"
export SSH_KEY=~/.ssh/id_rsa.pub
export AKS_RG="${AZURE_RESOURCE_GROUP}-aks"

az aks create \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --node-resource-group "${AKS_RG}" \
  --name "${CLUSTER_NAME}" \
  --enable-oidc-issuer \
  --enable-workload-identity \
  --location "${AZURE_REGION}" \
  --node-count 1 \
  --node-vm-size Standard_F4s_v2 \
  --nodepool-labels node.kubernetes.io/worker= \
  --ssh-key-value "${SSH_KEY}" \
  --admin-username "${AKS_WORKER_USER_NAME}" \
  --os-sku Ubuntu
```

Download kubeconfig

```bash
az aks get-credentials \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --name "${CLUSTER_NAME}"
```

### Deploy Cloud API Adaptor

Create CAA identity

```bash
export AZURE_WORKLOAD_IDENTITY_NAME="caa-identity"

az identity create \
  --name "${AZURE_WORKLOAD_IDENTITY_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --location "${AZURE_REGION}"

export USER_ASSIGNED_CLIENT_ID="$(az identity show \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --name "${AZURE_WORKLOAD_IDENTITY_NAME}" \
  --query 'clientId' \
  -otsv)"
```

Go back to the CAA directory

```bash
cd $BASEDIR/cloud-api-adaptor
```

Annotate CAA Service Account with workload identity's `CLIENT_ID`

```bash
cat <<EOF > install/overlays/azure/workload-identity.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: cloud-api-adaptor-daemonset
  namespace: confidential-containers-system
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cloud-api-adaptor
  namespace: confidential-containers-system
  annotations:
    azure.workload.identity/client-id: "$USER_ASSIGNED_CLIENT_ID"
EOF
```

Assign roles for CAA to create VMs and Networks

```
az role assignment create \
  --role "Virtual Machine Contributor" \
  --assignee "$USER_ASSIGNED_CLIENT_ID" \
  --scope "/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourcegroups/${AZURE_RESOURCE_GROUP}"
```

```
az role assignment create \
  --role "Reader" \
  --assignee "$USER_ASSIGNED_CLIENT_ID" \
  --scope "/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourcegroups/${AZURE_RESOURCE_GROUP}"
```

```
az role assignment create \
  --role "Network Contributor" \
  --assignee "$USER_ASSIGNED_CLIENT_ID" \
  --scope "/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourcegroups/${AKS_RG}"
```

Create federated credentials for the CAA Service Account

```
export AKS_OIDC_ISSUER="$(az aks show \
  --name "$CLUSTER_NAME" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --query "oidcIssuerProfile.issuerUrl" \
  -otsv)"

az identity federated-credential create \
  --name caa-fedcred \
  --identity-name caa-identity \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --issuer "${AKS_OIDC_ISSUER}" \
  --subject system:serviceaccount:confidential-containers-system:cloud-api-adaptor \
  --audience api://AzureADTokenExchange
```

Export VNet and Subnet ID from aks cluster

```bash
export AZURE_VNET_NAME=$(az network vnet list \
  --resource-group "${AKS_RG}" \
  --query "[0].name" \
  --output tsv)

export AZURE_SUBNET_ID=$(az network vnet subnet list \
  --resource-group "${AKS_RG}" \
  --vnet-name "${AZURE_VNET_NAME}" \
  --query "[0].id" \
  --output tsv)
```

Set TDX instance size

```bash
export AZURE_INSTANCE_SIZE="Standard_DC2es_v5"
```

Populate CAA Kustomize file

```bash
export registry="quay.io/confidential-containers"

cat <<EOF > install/overlays/azure/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
bases:
- ../../yamls
images:
- name: cloud-api-adaptor
  newName: "${registry}/cloud-api-adaptor"
  newTag: latest
generatorOptions:
  disableNameSuffixHash: true
configMapGenerator:
- name: peer-pods-cm
  namespace: confidential-containers-system
  literals:
  - CLOUD_PROVIDER="azure"
  - AZURE_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID}"
  - AZURE_REGION="${AZURE_REGION}"
  - AZURE_INSTANCE_SIZE="${AZURE_INSTANCE_SIZE}"
  - AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP}"
  - AZURE_SUBNET_ID="${AZURE_SUBNET_ID}"
  - AZURE_IMAGE_ID="${AZURE_IMAGE_ID}"
secretGenerator:
- name: peer-pods-secret
  namespace: confidential-containers-system
  literals: []
- name: ssh-key-secret
  namespace: confidential-containers-system
  files:
  - id_rsa.pub
patchesStrategicMerge:
- workload-identity.yaml
EOF
```

Copy your `SSH_KEY` to the CAA directory

```bash
cp $SSH_KEY install/overlays/azure/id_rsa.pub
```

Deploy CAA

```
CLOUD_PROVIDER=azure make deploy
```

## Deploy KBS

Clone KBS in the right commit:

```bash
cd $BASEDIR
git clone https://github.com/iaguis/kbs -b iaguis/add-az-tdx-vtpm-tee
cd kbs && git checkout c96b6b69da6bebd558e0704d0ce446f0a5dfdf64
```

Build KBS docker image

```bash
my_org=myorg

kbs_image="ghcr.io/${my_org}/kbs:tdx-demo"
docker build -f docker/Dockerfile -t "$kbs_image" .
docker push "$kbs_image"
```

Create keys and config files

```bash
openssl genpkey -algorithm ed25519 > kbs.key
openssl pkey -in kbs.key -pubout -out kbs.pem
cat <<EOF > ./kbs.toml
insecure_http = true
insecure_api = false

sockets = ["0.0.0.0:8080"]
auth_public_key = "/kbs.pem"
EOF
```

Create configmaps and secrets

```bash
kubectl create configmap --from-file kbs.toml kbs-config
kubectl create secret generic --from-file kbs.key kbs-key
kubectl create secret generic --from-file kbs.pem kbs-pem
```

Deploy KBS

```bash
cat <<EOF > ./kbs.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app: kbs
  name: kbs
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kbs
  template:
    metadata:
      labels:
        app: kbs
    spec:
      containers:
      - image: ${kbs_image}
        imagePullPolicy: Always
        name: kbs
        command:
        - /usr/local/bin/kbs
        ports:
        - containerPort: 8080
          protocol: TCP
        env:
        - name: KBS_CONFIG_FILE
          value: "/kbs.toml"
        volumeMounts:
        - name: kbs-config
          mountPath: /kbs.toml
          subPath: kbs.toml
        - name: kbs-pem
          mountPath: /kbs.pem
          subPath: kbs.pem
        - name: kbs-key
          mountPath: /kbs.key
          subPath: kbs.key
      volumes:
      - name: kbs-config
        configMap:
          name: kbs-config
      - name: kbs-pem
        secret:
          secretName: kbs-pem
      - name: kbs-key
        secret:
          secretName: kbs-key
EOF
kubectl apply -f ./kbs.yaml
```

Expose KBS

```bash
kubectl expose deployment kbs
cat <<EOF > ./kbs-nodeport.yaml
apiVersion: v1
kind: Service
metadata:
  name: kbs-nodeport
spec:
  type: NodePort
  selector:
    app: kbs
  ports:
    - port: 8080
      targetPort: 8080
      nodePort: 30080
EOF
kubectl apply -f kbs-nodeport.yaml
```

Get node IP

```bash
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo $NODE_IP
```

Edit CAA configmap to refer to the KBS Node IP

```bash
kubectl -n confidential-containers-system edit configmap peer-pods-cm
```

Add a variable like so substituting for the real `$NODE_IP`

```bash
AA_KBC_PARAMS: cc_kbc::http://${NODE_IP}:30080
```

Delete CAA Pod so it picks up the new configuration

```bash
kubectl -n confidential-containers-system delete pod -l app=cloud-api-adaptor
```

## Run demo

Clone and enter this repo

```bash
cd $BASEDIR
git clone https://github.com/kinvolk/tdx-demo-v2.git
cd tdx-demo-v2
```

### Requirements

Create and activate a python virtual env (tested w/ 3.11):

```bash
pip install -r requirements.txt
```

#### Encrypt

A CSV `df_enc.csv` encrypted w/ a symmetric random key `df_enc.key` will be produced:

```bash
python3 ./encrypt.py
```

#### Upload encryption key to KBS

```bash
KBS_POD=$(kubectl get pod -l app=kbs -o jsonpath="{.items[0].metadata.name}")
kubectl exec "$KBS_POD" -it -- mkdir -p /opt/confidential-containers/kbs/repository/default/key/
kubectl cp df_enc.key "$KBS_POD":/opt/confidential-containers/kbs/repository/default/key/secretkey
```

#### Deploy

```bash
demo_image="ghcr.io/${my_org}/tdx-demo:r1"
docker build -t "$demo_image" .
docker push "$demo_image"
cat <<EOF > ./tdx-demo.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: tdx-demo
spec:
  template:
    spec:
      runtimeClassName: kata-remote
      containers:
      - name: tdx-demo
        image: $demo_image
      restartPolicy: Never
EOF
kubectl apply -f ./tdx-demo.yaml
```

Checking the logs

```bash
kubectl logs jobs/tdx-demo
```

You should see the following output

```
shape: (1, 1)
┌────────┐
│ secret │
│ ---    │
│ i64    │
╞════════╡
│ 6      │
└────────┘
```
